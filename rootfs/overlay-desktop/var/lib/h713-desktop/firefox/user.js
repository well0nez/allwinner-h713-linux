// user.js of the browser mode's Firefox profile (h713-browser.service). Firefox applies it at every start.
// Every name below was looked up in Firefox ESR 140.15 (Debian trixie): libxul's static prefs or the omni.ja defaults. Not here:
// media.ffmpeg.vaapi.enabled, which ESR 140 no longer has (VA-API is on by default, behind the blocklist).
//
// Hardware video decoding through ffmpeg's VA-API path with the driver of rootfs/libva (the unit's drop-in names it). Panfrost is on no
// vendor whitelist, so the blocklist is overridden. Inside Firefox's decoder sandbox the VA-API device context cannot be made and Firefox
// decodes in software (measured, H4); the hardware path needs MOZ_DISABLE_RDD_SANDBOX=1, a commented line in h713-browser.service.
user_pref("media.hardware-video-decoding.force-enabled", true);
user_pref("widget.dmabuf.force-enabled", true);
// A wall seen from three metres: a TV interface, not a laptop's. At 1920x1080 the page is laid out as for 960x540 CSS pixels, a 16 px text is a
// 32 px letter (Marco 16.10.2026: "hardly readable"). Firefox takes the factor as a string; the browser and the desktop's Firefox window share it.
user_pref("layout.css.devPixelsPerPx", "2.0");
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
// The first start-up work nobody sees (acceptance of 16.10.2026, F4: Firefox needed 9 to 13 s to its first picture on this board, four
// Cortex-A53 and one GiB). What the start page fetches and parses (Pocket stories, sponsored tiles), the telemetry, the remote experiments
// (Normandy), the region and connectivity lookups, and the spare content process Firefox starts in advance (about 100 MiB of 924) are off.
// The page keeps its search and shortcut tiles. These are the candidates that cost nothing a person sees; what they save is for a measurement
// on the box (time from the unit's start to the window's first map, with and without the block), not an assumption.
user_pref("browser.newtabpage.activity-stream.feeds.section.topstories", false);
user_pref("browser.newtabpage.activity-stream.feeds.system.topstories", false);
user_pref("browser.newtabpage.activity-stream.discoverystream.enabled", false);
user_pref("browser.newtabpage.activity-stream.showSponsored", false);
user_pref("browser.newtabpage.activity-stream.showSponsoredTopSites", false);
user_pref("toolkit.telemetry.enabled", false);
user_pref("toolkit.telemetry.unified", false);
user_pref("datareporting.healthreport.uploadEnabled", false);
user_pref("app.normandy.enabled", false);
user_pref("browser.region.update.enabled", false);
user_pref("network.connectivity-service.enabled", false);
user_pref("dom.ipc.processPrelaunch.enabled", false);
