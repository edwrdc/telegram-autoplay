# Channel video autoplay

An experimental Python plugin for AyuGram Full on Android. Open a video in a
regular private chat, group, channel, or forum topic and let it finish. The
plugin finds the next newer video in that chat or topic and starts it in the
same viewer. No separate Telegram client, playlist, or manual download is needed.

Device testing is in progress. Successful autoplay is not yet confirmed. Local
tests use SDK and Java stand-ins and do not prove native player compatibility.

## Install from the catalog

After the plugin and index have been pushed to GitHub:

1. In AyuGram Full, open the plugin catalog and add this repository:
   `https://github.com/edwrdc/telegram-autoplay/tree/main`
2. If prompted, enable **Unknown sources** in plugin settings. Review the
   security analysis and install **Channel video autoplay**.
3. Enable the plugin. Its settings contain **Continuous video playback**,
   which is on by default and persists across restarts.
4. Open a video in a supported chat or topic. Enter fullscreen or landscape mode
   as you normally would, then let the video finish.

The catalog requires an AyuGram Full build with exteraGram plugin support and
SDK 1.4.5.3 or newer. Builds without Git repository support can install the
[`channel_video_autoplay.plugin`](plugins/channel_video_autoplay.plugin) file
through their normal plugin-file installation flow. No ADB is required.

## Playback rules

- Playback follows increasing message IDs, from older posts to newer
  posts. It does not follow the visual direction of the media gallery.
- Text, photos, animations, round video messages, and web embeds are skipped.
  Short and long videos, including files that Telegram recognizes as videos,
  use the native player. Unsupported codecs remain unsupported.
- History loads in pages of 100 messages, so autoplay can continue beyond the
  viewer's cached media. It stays in the original chat and account.
- Forum topics use topic-specific history. Playback stops at the last video
  in that topic instead of continuing into another topic.
- Secret Chats are excluded because server history cannot access their local
  messages. Other regular private chats and groups are supported.
- Short clips stop looping while autoplay is enabled. Disabling or unloading
  the plugin restores the player's previous looping setting.
- The plugin changes videos inside the existing viewer. It does not close the
  viewer or request a different orientation. Fullscreen continuity still needs
  testing on the tablet. Gallery counters can be approximate after the plugin
  inserts a video beyond the cached media.
- At the chat or topic's end, autoplay stops. It does not wait for future posts.
  History errors and 20-second request timeouts stop the current advance without
  skipping a video or repeatedly retrying. Replay the video to try again.
- Closing the viewer, disabling the plugin, or unloading it cancels pending
  history requests. Replies are ignored if the viewer, video, account, or topic changed,
  or if you resumed playback manually.

Normal Telegram streaming and caching still use storage and network data. If a
video cannot stream, the native downloader loads it into Telegram's cache before
playback. History lookups and buffering can cause gaps between videos.

## Develop on Linux

Python 3.11 or newer is sufficient for the local checks. No packages are needed.
The Android app supplies the SDK and Java imports at runtime.

```sh
python3 build_index.py
python3 build_index.py --check
python3 -m unittest discover -s tests -v
```

Edit `plugins/channel_video_autoplay.plugin`. Before publishing an update,
increase its `__version__`, regenerate the index, run the checks, and commit
both the plugin and `extera-plugins.json`. The index contains the file's SHA-256
and byte size. The catalog rejects mismatched files. GitHub Actions checks the
tests and index on pushes and pull requests.

Push the commit, refresh the tablet's catalog, install the update, and reload
the plugin. The catalog otherwise caches its index for up to ten minutes.

## Tablet checks and error reports

On the Samsung Galaxy Tab A9 SM-X115:

1. Use a channel with several videos separated by text and photos. Check that
   the next newer video starts, not an older one or a video from another chat.
2. Include a clip under 30 seconds, a long landscape video, a video sent as a
   file, and an uncached video. Check fullscreen and orientation between them.
3. Test more than 100 non-video posts between videos and the final video in
   the channel. Open videos from both channel messages and shared media.
4. While history is loading, close and reopen the viewer, swipe to another
   video, switch accounts, or replay manually. Check that an old reply does not
   change the video you selected.
5. Disable autoplay, restart AyuGram, and confirm the setting persists. Re-enable
   it, background and resume the app, and check that short clips still advance.
6. Test an offline connection and plugin unload. Confirm that Secret Chats,
   round video messages, and web players are unchanged.
7. Test private chats with incoming and outgoing videos, basic groups,
   supergroups, and forum topics including General. Check that playback stays
   in the same chat and, when opened in a topic, the same topic.

To copy diagnostics without ADB:

1. Update to version 0.1.4 or newer and enable the plugin.
2. Reproduce the playback problem.
3. Close the video viewer and open this plugin's settings.
4. Tap **Copy diagnostics**, then paste the text into your error report.

Do not reload the plugin between reproducing the problem and copying diagnostics.
It keeps the last 100 log entries in memory and resets them on plugin load.
The SDK otherwise writes these logs to Android logcat, not an in-app log screen.

Include logs even if there is no traceback. They report player hooks, ready and
ended states, loop overrides, and reasons for ignoring a video. Routine
diagnostics omit channel IDs and message content. Review tracebacks before
sharing them. Include the
AyuGram Full version/build, SDK version, Android version, plugin version, how
you opened the video, and whether it streamed or was cached. Do not include
private channel content, access hashes, or account credentials.

An internal error disables autoplay until you reload the plugin. A load error
usually means an SDK or private viewer API differs from the source below.

## Integration references

The implementation follows the [exteraGram SDK docs](https://plugins.exteragram.app/docs),
also indexed at [Context7 `/websites/plugins_exteragram_app`](https://context7.com/websites/plugins_exteragram_app).
Catalog format and installation follow the [repository documentation](https://plugins.exteragram.app/docs/plugin-repositories).

Player hooks were checked against
[AyuGram PhotoViewer at 7013145](https://github.com/AyuGram/AyuGram4A/blob/7013145676d36d82ee13c02a89f72097b7490dcd/TMessagesProj/src/main/java/org/telegram/ui/PhotoViewer.java)
and [exteraGram PhotoViewer at 6f78031](https://github.com/exteraSquad/exteraGram/blob/6f78031aafd7f27e0dfaa31a207715569a6df1a2/TMessagesProj/src/main/java/org/telegram/ui/PhotoViewer.java).
The plugin hooks `updatePlayerState(boolean, int)`, all available
`preparePlayer` overloads, `onResume`, and `closePhoto`. It calls `setImageIndex(int)`,
`setImages()`, and `onActionClick(boolean)` through reflection. A positive UI
delay lets the native completion handler finish before the plugin changes videos.
These are private APIs, not a stable SDK playback interface.
Topic lookup uses the account-aware `MessageObject.getTopicId(account, message,
sureIsForum)` signature exposed by exteraGram 13.1.1.

## License

MIT. See [LICENSE](LICENSE).
