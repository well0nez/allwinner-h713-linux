// user.js of the browser mode's Firefox profile (h713-browser.service). Firefox applies it at every start.
// Every name below was looked up in Firefox ESR 140.15 (Debian trixie): libxul's static prefs or the omni.ja defaults. Not here:
// media.ffmpeg.vaapi.enabled, which ESR 140 no longer has (VA-API is on by default, behind the blocklist).
//
// Hardware video decoding through ffmpeg's VA-API path with the driver of rootfs/libva (the unit's drop-in names it). Panfrost is on no
// vendor whitelist, so the blocklist is overridden. Inside Firefox's decoder sandbox the VA-API device context cannot be made and Firefox
// decodes in software (measured, H4); the hardware path needs MOZ_DISABLE_RDD_SANDBOX=1, a commented line in h713-browser.service.
user_pref("media.hardware-video-decoding.force-enabled", true);
user_pref("widget.dmabuf.force-enabled", true);
// Sound: ALSA `default`, the DSP bridge, like Kodi - no PulseAudio or PipeWire runs on this image (the media profile masks the PipeWire user
// units and leaves pipewire-alsa out). Asked for by name, Firefox does not try a sound server first.
user_pref("media.cubeb.backend", "alsa");
// One GiB of RAM (docs/hardware.md): ESR 140 defaults to 8 content processes (4 web-isolated). Two each is the first guess; H4 measures the
// RSS and the page's behaviour, the numbers are the report's to change.
user_pref("dom.ipc.processCount", 2);
user_pref("dom.ipc.processCount.webIsolated", 2);
// A projector is not a laptop: no first-run pages, no default-browser question, no auto-update, no data submission, and no restore page
// after the socket was closed under Firefox (the unit's stop).
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.aboutwelcome.enabled", false);
user_pref("browser.sessionstore.resume_from_crash", false);
user_pref("toolkit.startup.max_resumed_crashes", -1);
user_pref("app.update.auto", false);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
