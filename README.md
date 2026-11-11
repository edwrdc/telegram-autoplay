# Channel video autoplay

This project is investigating a Python plugin for AyuGram Full on Android.
**There is no working plugin yet.**
The plugin repository index is empty until a working plugin is available.

## Integration findings

The [exteraGram plugin SDK](https://plugins.exteragram.app/docs/xposed-hooking)
can hook Java methods and access private fields. The viewer code inspected was
[exteraGram at 6f78031](https://github.com/exteraSquad/exteraGram/blob/6f78031aafd7f27e0dfaa31a207715569a6df1a2/TMessagesProj/src/main/java/org/telegram/ui/PhotoViewer.java).
It may not match the AyuGram APK installed on a device.

The viewer handles playback completion in the private
`updatePlayerState(boolean, int)` method. It uses `setImageIndex(int)` to
change the displayed item. The viewer list may contain photos, may not include
all channel media, and may include media from a migrated chat. A plugin must
load missing media, select the next playable video in message order within
the original channel, and start playback without racing the end handler.
The SDK does not provide a documented high-level API for this sequence.

The Android player integration and behavior on AyuGram Full are not verified.
The internal method names can change between app builds.

## Next implementation steps

1. Identify the exact AyuGram Full build and inspect its matching player code.
2. Hook playback completion only for videos in broadcast channels. Ignore
   callbacks from closed viewers, previews, and other players.
3. Load and select the next video, including when it is outside the viewer
   cache. Stop at the end or on network failure. Keep the original channel and
   account across asynchronous callbacks.
4. Start the selected video in the existing viewer and add a persistent toggle.
5. Run the device tests below and verify installation and plugin unload.

## Device test plan

Test on a channel with videos separated by text and photos. Include short and
long videos, and a video posted as a file. Test with landscape orientation and
fullscreen enabled. Check that playback follows message order and stays in the
same channel.

Also test the last video, an offline connection, disabling autoplay while a
video is playing, closing the viewer, switching accounts, and manually seeking
to the end. Verify that ordinary chats and other players are unaffected.

## License

MIT. See [LICENSE](LICENSE).
