"""Desktop checks with SDK/Java stand-ins. These do not test an Android player."""

import logging
from pathlib import Path
import runpy
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch


class BasePlugin:
    def __init__(self):
        self.logger = Mock(spec=[*dir(logging.Logger), "add_handler", "remove_handler"])
        self.get_setting = Mock(return_value=True)
        self.hook_method = Mock(side_effect=lambda *args: Mock())
        self.hook_all_methods = Mock(side_effect=lambda *args: [Mock()])


class JavaInteger(int):
    TYPE = int


class JavaBoolean:
    TYPE = bool

    def __new__(cls, value):
        return bool(value)


class DocumentMedia:
    pass


class JavaList(list):
    def size(self):
        return len(self)

    def get(self, index):
        return self[index]

    def add(self, index, value):
        self.insert(index, value)


class Player:
    def __init__(self, looping=True):
        self.looping = looping
        self.playing = False

    def isLooping(self):
        return self.looping

    def setLooping(self, value):
        self.looping = value

    def isPlaying(self):
        return self.playing


def row(message_id, video=True, channel=123, streamable=True):
    return NS(id=message_id, peer_id=NS(channel_id=channel),
              media=DocumentMedia() if video else None, video=video, streamable=streamable)


class Message:
    def __init__(self, account, raw, generate_layout=False, check_media=True):
        self.currentAccount = account
        self.messageOwner = raw
        self.scheduled = False
        self.forceSeekTo = -1.0

    def getId(self):
        return self.messageOwner.id

    def getDialogId(self):
        return -self.messageOwner.peer_id.channel_id

    def getDocument(self):
        return self.messageOwner.media

    def isVideo(self):
        return self.messageOwner.video

    @staticmethod
    def isVideoMessage(raw):
        return raw.video


def module(**attrs):
    result = ModuleType("sdk_stub")
    result.__dict__.update(attrs)
    return result


sdk_modules = {
    "android_utils": module(run_on_ui_thread=Mock(), copy_to_clipboard=Mock()),
    "base_plugin": module(BasePlugin=BasePlugin, MethodHook=object),
    "client_utils": module(send_request=Mock()),
    "hook_utils": module(get_private_field=getattr,
                         set_private_field=lambda obj, name, value: setattr(obj, name, value) or True),
    "java.lang": module(Boolean=JavaBoolean, Integer=JavaInteger),
    "org.telegram.messenger": module(
        FileLoader=Mock(PRIORITY_NORMAL=1), MediaDataController=NS(MEDIA_PHOTOVIDEO=0),
        MessageObject=Message, MessagesController=Mock(), UserConfig=NS(selectedAccount=1),
    ),
    "org.telegram.tgnet": module(
        ConnectionsManager=Mock(),
        TLRPC=NS(TL_messageMediaDocument=DocumentMedia, TL_messages_getHistory=NS),
    ),
    "org.telegram.ui": module(PhotoViewer=Mock(spec=["getClass", "hasInstance", "getInstance"])),
    "ui.settings": module(Switch=lambda **kwargs: kwargs, Text=lambda **kwargs: kwargs),
}
with patch.dict("sys.modules", sdk_modules):
    plugin_module = runpy.run_path(str(
        Path(__file__).resolve().parents[1] / "plugins/channel_video_autoplay.plugin"
    ))
Plugin = plugin_module["ChannelVideoAutoplayPlugin"]


class AutoplayTests(unittest.TestCase):
    def setUp(self):
        self.queue = []
        self.callbacks = []
        self.requests = []
        self.ui = sdk_modules["android_utils"].run_on_ui_thread
        self.ui.side_effect = lambda fn, delay=0: self.queue.append((delay, fn))
        self.clipboard = sdk_modules["android_utils"].copy_to_clipboard
        self.clipboard.reset_mock()
        self.send = sdk_modules["client_utils"].send_request
        self.send.reset_mock()
        self.send.side_effect = self.send_request
        self.api = sdk_modules["org.telegram.messenger"]
        self.api.UserConfig.selectedAccount = 1
        self.api.MessagesController.reset_mock()
        self.api.MessagesController.getInstance.return_value.getChat.return_value = NS(
            broadcast=True, megagroup=False,
        )
        self.api.FileLoader.reset_mock()
        self.connections = sdk_modules["org.telegram.tgnet"].ConnectionsManager
        self.connections.reset_mock()
        self.viewer_class = Mock(spec=["getDeclaredField", "getDeclaredMethod"])
        self.photo_viewer = sdk_modules["org.telegram.ui"].PhotoViewer
        self.photo_viewer.reset_mock()
        self.photo_viewer.getClass.return_value = self.viewer_class
        self.photo_viewer.hasInstance.return_value = False
        self.plugin = Plugin()
        self.plugin.on_plugin_load()
        self.run_queued(0)
        message = Message(1, row(10))
        self.viewer = NS(
            currentMessageObject=message, currentAccount=1, currentDialogId=-123,
            classGuid=5, videoPlayer=Player(), inPreview=False, currentEditMode=0,
            isInline=False, switchingInlineMode=False, imagesArr=JavaList([message]),
            imagesByIds=[NS(put=Mock())], currentIndex=0, opennedFromMedia=False,
            sharedMediaType=0, visible=True,
        )
        self.viewer.isVisible = lambda: self.viewer.visible
        self.plugin._index = NS(invoke=Mock(side_effect=self.select))
        self.plugin._images = NS(invoke=Mock())
        self.plugin._action = NS(invoke=Mock(side_effect=self.start))

    def send_request(self, request, callback, *, account):
        self.requests.append((account, request))
        self.callbacks.append(callback)
        return len(self.requests)

    def run_queued(self, delay):
        index = next(i for i, item in enumerate(self.queue) if item[0] == delay)
        self.queue.pop(index)[1]()

    def select(self, viewer, index):
        viewer.currentIndex = index
        viewer.currentMessageObject = viewer.imagesArr[index]
        viewer.videoPlayer = None

    def start(self, viewer, download):
        self.assertFalse(download)
        if viewer.currentMessageObject.messageOwner.streamable:
            viewer.videoPlayer = Player()
            self.plugin._update_loop(viewer)

    def begin(self):
        self.plugin._ended(self.viewer)
        self.run_queued(1)

    def reply(self, rows=(), error=None, callback=-1):
        self.callbacks[callback](NS(messages=JavaList(rows)), error)
        self.run_queued(0)

    def test_next_is_nearest_newer_video_in_same_channel(self):
        self.begin()
        self.reply([row(50), row(11, channel=999), row(12, video=False), row(14), row(9)])
        self.assertEqual(self.viewer.currentMessageObject.getId(), 14)
        self.assertEqual(self.viewer.currentMessageObject.getDialogId(), -123)
        self.assertEqual(self.viewer.currentMessageObject.forceSeekTo, 0.0)
        self.plugin._images.invoke.assert_called_once_with(self.viewer)
        self.assertFalse(self.viewer.videoPlayer.looping)
        self.assertIsNone(self.plugin._pending)

    def test_request_uses_reverse_history_and_explicit_account(self):
        self.begin()
        account, req = self.requests[0]
        self.assertEqual(account, 1)
        self.assertEqual((req.offset_id, req.add_offset, req.limit, req.min_id), (11, -100, 100, 0))
        self.api.MessagesController.getInstance.return_value.getInputPeer.assert_called_with(-123)

    def test_reflection_uses_java_classes_not_chaquopy_wrappers(self):
        self.assertTrue(self.plugin._alive)
        self.assertIs(self.plugin._viewer_class, self.viewer_class)
        self.photo_viewer.getClass.assert_called_once_with()
        self.viewer_class.getDeclaredField.assert_any_call("currentMessageObject")
        self.viewer_class.getDeclaredMethod.assert_any_call(
            "updatePlayerState", JavaBoolean.TYPE, JavaInteger.TYPE,
        )
        self.plugin.hook_all_methods.assert_any_call(
            self.viewer_class, "preparePlayer", unittest.mock.ANY,
        )
        self.plugin.hook_all_methods.assert_any_call(
            self.viewer_class, "closePhoto", unittest.mock.ANY,
        )

    def test_load_does_not_require_four_argument_prepare_player(self):
        def lookup(name, *types):
            if name == "preparePlayer":
                raise RuntimeError("NoSuchMethodException: preparePlayer(Uri, boolean, boolean, SavedFilterState)")
            return Mock()

        self.viewer_class.getDeclaredMethod.side_effect = lookup
        plugin = Plugin()
        plugin.on_plugin_load()
        self.assertTrue(plugin._alive)
        self.assertEqual([call.args[1] for call in plugin.hook_all_methods.call_args_list],
                         ["preparePlayer", "closePhoto"])

    def test_prepare_hook_handles_nested_overloads_without_losing_original_looping(self):
        hook = self.plugin.hook_all_methods.call_args_list[0].args[2]
        player = self.viewer.videoPlayer
        for arity in (3, 4, 5):
            with self.subTest(arity=arity):
                param = Mock(thisObject=self.viewer, args=[None] * arity)
                param.hasThrowable.return_value = False
                hook.after_hooked_method(param)
                self.assertFalse(player.looping)
        self.plugin._restore_loop()
        self.assertTrue(player.looping)

    def test_prepare_diagnostics_report_hook_and_loop_override(self):
        hook = self.plugin.hook_all_methods.call_args_list[0].args[2]
        param = Mock(thisObject=self.viewer)
        param.hasThrowable.return_value = False
        hook.after_hooked_method(param)
        self.plugin.logger.info.assert_any_call("Autoplay player preparation/resume hook fired")
        self.plugin.logger.info.assert_any_call("Autoplay loop override applied; looping=False")
        self.assertFalse(self.viewer.videoPlayer.looping)

    def test_scope_rejection_is_logged_without_channel_ids(self):
        self.viewer.currentDialogId = 0
        self.plugin._update_loop(self.viewer)
        diagnostic = self.plugin.logger.info.call_args.args[0]
        self.assertIn("scope mismatch", diagnostic)
        self.assertIn("viewer_dialog_matches=False", diagnostic)
        self.assertNotIn("-123", diagnostic)
        self.assertTrue(self.viewer.videoPlayer.looping)

    def test_missing_native_player_is_logged(self):
        self.viewer.videoPlayer = None
        self.plugin._update_loop(self.viewer)
        self.plugin.logger.info.assert_any_call("Autoplay waiting: native video player is not attached")

    def test_copy_diagnostics_uses_recent_plugin_logs_and_preserves_tracebacks(self):
        self.plugin.logger.add_handler.assert_called_once_with(self.plugin._capture_log)
        handler = self.plugin.logger.add_handler.call_args.args[0]
        for index in range(101):
            handler(NS(text=f"entry {index}"))
        self.assertEqual(len(self.plugin._diagnostics), 100)
        self.assertEqual(self.plugin._diagnostics[0], "entry 1")
        handler(NS(text="Traceback:\nRuntimeError: example"))
        settings = self.plugin.create_settings()
        self.assertEqual(settings[1]["text"], "Copy diagnostics")
        settings[1]["on_click"](None)
        copied = self.clipboard.call_args.args[0]
        self.assertTrue(copied.startswith(f"Channel video autoplay {plugin_module['__version__']}\n"))
        self.assertNotIn("entry 0\n", copied)
        self.assertIn("entry 100\n", copied)
        self.assertTrue(copied.endswith("Traceback:\nRuntimeError: example"))

    def test_copy_diagnostics_before_plugin_load_explains_how_to_capture(self):
        plugin = Plugin()
        plugin._copy_diagnostics(None)
        self.assertIn("Enable the plugin and reproduce the problem first",
                      self.clipboard.call_args.args[0])

    def test_unload_detaches_diagnostic_handler_but_keeps_report(self):
        self.plugin._capture_log(NS(text="Last diagnostic"))
        self.plugin.on_plugin_unload()
        self.plugin.logger.remove_handler.assert_called_once_with(self.plugin._capture_log)
        self.plugin._copy_diagnostics(None)
        self.assertIn("Last diagnostic", self.clipboard.call_args.args[0])

    def test_skips_entire_nonvideo_pages(self):
        self.begin()
        self.reply([row(i, video=False) for i in range(110, 10, -1)])
        self.run_queued(350)
        self.assertEqual(self.requests[1][1].offset_id, 111)
        self.reply([row(111, video=False), row(112)])
        self.assertEqual(self.viewer.currentMessageObject.getId(), 112)

    def test_end_of_channel_stops_without_replaying(self):
        self.begin()
        self.reply([row(10), row(9)])
        self.assertIsNone(self.plugin._pending)
        self.plugin._action.invoke.assert_not_called()
        self.assertEqual(len(self.requests), 1)

    def test_foreign_channel_cannot_advance_the_history_cursor(self):
        self.begin()
        self.reply([row(99, channel=555)])
        self.assertIsNone(self.plugin._pending)
        self.assertFalse(any(delay == 350 for delay, _ in self.queue))
        self.plugin._index.invoke.assert_not_called()

    def test_duplicate_completion_is_ignored_while_loading(self):
        self.begin()
        self.plugin._ended(self.viewer)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual([delay for delay, _ in self.queue], [20000])

    def test_stale_response_cannot_take_over_viewer(self):
        for field, value in (
            ("visible", False), ("classGuid", 99), ("videoPlayer", Player()),
            ("currentMessageObject", Message(1, row(30))), ("inPreview", True),
        ):
            with self.subTest(field=field):
                old = getattr(self.viewer, field)
                self.begin()
                setattr(self.viewer, field, value)
                self.reply([row(11)])
                self.plugin._index.invoke.assert_not_called()
                self.assertIsNone(self.plugin._pending)
                setattr(self.viewer, field, old)

    def test_account_switch_and_manual_replay_cancel_autoplay(self):
        self.begin()
        self.api.UserConfig.selectedAccount = 2
        self.reply([row(11)])
        self.plugin._index.invoke.assert_not_called()
        self.api.UserConfig.selectedAccount = 1
        self.begin()
        self.viewer.videoPlayer.playing = True
        self.reply([row(11)])
        self.plugin._index.invoke.assert_not_called()

    def test_channel_only_and_native_video_only(self):
        for field, value in (("inPreview", True), ("currentEditMode", 1),
                             ("isInline", True), ("switchingInlineMode", True)):
            with self.subTest(field=field):
                setattr(self.viewer, field, value)
                self.assertFalse(self.plugin._eligible(self.viewer))
                setattr(self.viewer, field, False if field != "currentEditMode" else 0)
        chat = self.api.MessagesController.getInstance.return_value.getChat.return_value
        chat.megagroup = True
        self.assertFalse(self.plugin._eligible(self.viewer))
        chat.megagroup = False
        chat.broadcast = False
        self.assertFalse(self.plugin._eligible(self.viewer))
        chat.broadcast = True
        message = self.viewer.currentMessageObject
        for attribute, value in (("scheduled", True), ("currentAccount", 2)):
            old = getattr(message, attribute)
            setattr(message, attribute, value)
            self.assertFalse(self.plugin._eligible(self.viewer))
            setattr(message, attribute, old)
        message.messageOwner.media = NS(webpage="not a direct channel video")
        self.assertFalse(self.plugin._eligible(self.viewer))

    def test_short_clip_looping_is_restored_when_disabled(self):
        player = self.viewer.videoPlayer
        self.plugin._update_loop(self.viewer)
        self.plugin._update_loop(self.viewer)
        self.assertFalse(player.looping)
        self.begin()
        self.plugin._toggle(False)
        self.run_queued(0)
        self.assertTrue(player.looping)
        self.assertIsNone(self.plugin._pending)
        self.connections.getInstance.return_value.cancelRequest.assert_called_with(1, True)
        self.reply([row(11)])
        self.plugin._index.invoke.assert_not_called()

    def test_enabling_updates_the_open_viewer_through_its_static_api(self):
        self.photo_viewer.hasInstance.return_value = True
        self.photo_viewer.getInstance.return_value = self.viewer
        self.plugin._toggle(True)
        self.run_queued(0)
        self.assertTrue(self.plugin._alive)
        self.assertFalse(self.viewer.videoPlayer.looping)
        self.photo_viewer.getInstance.assert_called_once()

    def test_nonlooping_long_video_stays_nonlooping_on_unload(self):
        self.viewer.videoPlayer.looping = False
        self.plugin._update_loop(self.viewer)
        self.plugin.on_plugin_unload()
        self.run_queued(0)
        self.assertFalse(self.viewer.videoPlayer.looping)

    def test_resume_hook_disables_the_native_short_clip_loop_again(self):
        self.plugin._update_loop(self.viewer)
        self.viewer.videoPlayer.setLooping(True)  # Native PhotoViewer.onResume.
        param = Mock(thisObject=self.viewer)
        param.hasThrowable.return_value = False
        hook = self.plugin.hook_method.call_args_list[1].args[1]
        hook.after_hooked_method(param)
        self.assertFalse(self.viewer.videoPlayer.looping)
        self.plugin._restore_loop()
        self.assertTrue(self.viewer.videoPlayer.looping)

    def test_close_cancels_old_request_even_if_same_video_reopens(self):
        self.begin()
        plugin_module["LeaveHook"](self.plugin).before_hooked_method(NS(thisObject=self.viewer))
        self.begin()
        self.reply([row(11)], callback=0)
        self.plugin._index.invoke.assert_not_called()
        self.reply([row(12)])
        self.assertEqual(self.viewer.currentMessageObject.getId(), 12)

    def test_error_and_timeout_stop_without_skipping(self):
        self.begin()
        self.reply(error=NS(text="NETWORK_ERROR"))
        self.assertIsNone(self.plugin._pending)
        self.begin()
        self.run_queued(20000)  # Old timeout must not cancel the new request.
        self.assertIsNotNone(self.plugin._pending)
        self.run_queued(20000)
        self.assertIsNone(self.plugin._pending)
        self.connections.getInstance.return_value.cancelRequest.assert_called_with(2, True)
        self.reply([row(11)])
        self.plugin._index.invoke.assert_not_called()

    def test_send_error_stops_plugin_and_restores_looping(self):
        self.plugin._update_loop(self.viewer)
        self.send.side_effect = RuntimeError("SDK mismatch")
        self.begin()
        self.assertFalse(self.plugin._alive)
        self.assertTrue(self.viewer.videoPlayer.looping)
        self.assertIsNone(self.plugin._pending)

    def test_insertion_handles_both_gallery_directions(self):
        for descending in (False, True):
            with self.subTest(descending=descending):
                images = [Message(1, row(i, video=i != 12)) for i in (10, 12, 20)]
                if descending:
                    images.reverse()
                self.viewer.imagesArr = JavaList(images)
                self.viewer.opennedFromMedia = descending
                self.viewer.currentIndex = 2 if descending else 0
                self.viewer.currentMessageObject = self.viewer.imagesArr[self.viewer.currentIndex]
                self.viewer.videoPlayer = Player()
                self.begin()
                self.reply([row(15)])
                ids = [message.getId() for message in self.viewer.imagesArr]
                self.assertEqual(ids, [20, 15, 12, 10] if descending else [10, 12, 15, 20])
                self.assertEqual(self.viewer.currentMessageObject.getId(), 15)

    def test_cached_video_is_reused_but_migrated_chat_id_is_not(self):
        other_chat = Message(1, row(14, channel=555))
        cached = Message(1, row(14))
        self.viewer.imagesArr.extend([other_chat, cached])
        self.begin()
        self.reply([row(14)])
        self.assertIs(self.viewer.currentMessageObject, cached)
        self.assertEqual(len(self.viewer.imagesArr), 3)

    def test_nonstreamable_video_uses_native_download(self):
        self.viewer.sharedMediaType = 1
        self.begin()
        self.reply([row(11, streamable=False)])
        self.assertEqual(self.viewer.sharedMediaType, 0)
        message = self.viewer.currentMessageObject
        self.api.FileLoader.getInstance.return_value.loadFile.assert_called_once_with(
            message.getDocument(), message, 1, 0,
        )

    def test_failed_viewer_transition_stops_without_starting_wrong_video(self):
        self.plugin._index.invoke.side_effect = None
        self.begin()
        self.reply([row(11)])
        self.assertFalse(self.plugin._alive)
        self.plugin._action.invoke.assert_not_called()
        self.assertEqual(self.viewer.currentMessageObject.getId(), 10)

    def test_completion_hook_defers_transition_and_never_suppresses_native_handler(self):
        hook = plugin_module["PlaybackHook"](self.plugin)
        param = Mock(thisObject=self.viewer, args=[True, 3])
        param.hasThrowable.return_value = False
        hook.after_hooked_method(param)
        self.assertIsNone(self.plugin._pending)
        self.plugin.logger.info.assert_any_call("Autoplay player state=3, play_when_ready=True")
        param.args[1] = 4
        hook.after_hooked_method(param)
        self.plugin.logger.info.assert_any_call("Autoplay player state=4, play_when_ready=True")
        self.send.assert_not_called()
        param.setResult.assert_not_called()
        self.run_queued(1)
        self.assertEqual(len(self.requests), 1)

    def test_unsupported_api_fails_load_and_unhooks_partial_install(self):
        plugin = Plugin()
        prepared = Mock()
        plugin.hook_all_methods.side_effect = [[prepared], []]
        with self.assertRaisesRegex(RuntimeError, "viewer close"):
            plugin.on_plugin_load()
        self.assertFalse(plugin._alive)
        self.assertEqual(plugin._unhooks, [])
        self.assertEqual(plugin.hook_method.call_count, 2)
        prepared.unhook.assert_called_once()

    def test_missing_prepare_player_unhooks_partial_install(self):
        plugin = Plugin()
        installed = [Mock(), Mock()]
        plugin.hook_method.side_effect = installed
        plugin.hook_all_methods.side_effect = None
        plugin.hook_all_methods.return_value = []
        with self.assertRaisesRegex(RuntimeError, "preparePlayer"):
            plugin.on_plugin_load()
        self.assertFalse(plugin._alive)
        self.assertEqual(plugin._unhooks, [])
        for unhook in installed:
            unhook.unhook.assert_called_once()

    def test_unload_cancels_work_and_restores_short_clip(self):
        player = self.viewer.videoPlayer
        self.plugin._update_loop(self.viewer)
        unhooks = list(self.plugin._unhooks)
        self.begin()
        self.plugin.on_plugin_unload()
        self.run_queued(0)
        self.assertTrue(player.looping)
        for unhook in unhooks:
            unhook.unhook.assert_called_once()
        self.reply([row(11)])
        self.plugin._index.invoke.assert_not_called()

    def test_one_unhook_failure_does_not_skip_other_cleanup(self):
        self.plugin._update_loop(self.viewer)
        unhooks = list(self.plugin._unhooks)
        unhooks[0].unhook.side_effect = RuntimeError("Unhook error")
        self.plugin.on_plugin_unload()
        self.run_queued(0)
        for unhook in unhooks:
            unhook.unhook.assert_called_once()
        self.assertTrue(self.viewer.videoPlayer.looping)


if __name__ == "__main__":
    unittest.main()
