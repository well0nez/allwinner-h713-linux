#!/bin/sh
# second pass of the clean-stack device test in the same boot, with the launcher closed (the first pass ran under it)
B=/root/vp-bench
r() { echo "+ $*"; "$@"; echo "rc=$?"; }
r systemctl start h713-tv@video1; sleep 8
r h713-osd ctl launcher close; sleep 3
echo "=== state (picture on the wall)"
h713-tv ctl status | grep -E "^picture|^cover|^hdmi|frames:|^want"; sleep 2; h713-tv ctl status | grep -E "^hdmi|frames:"
dmesg | grep -E "hdmi: (the video plane|channel 0)" | tail -2 | cut -c1-200
$B verify hist --expect p1 2>/dev/null | grep -E "INFO histogram sum" | head -1 | cut -c1-200
echo "=== warp ring (risk): keystone"
r h713-warp ctl keystone set tl x 80; sleep 6; h713-warp ctl status | head -3; h713-tv ctl status | grep -E "^picture|^want|frames:"
journalctl -u h713-warp --no-pager -n 12 | cut -c1-200
dmesg | grep -iE "dma|import|panfrost|h713-drm" | tail -6 | cut -c1-200
r h713-warp ctl keystone set tl x 0; sleep 3
echo "=== client"
r systemctl start h713-kodi; sleep 30; r h713-tv ctl warp; h713-tv ctl status | grep -E "^picture|^want"
r systemctl stop h713-kodi; sleep 4
echo "=== way out"
r systemctl stop h713-tv@video1; sleep 2; journalctl -u "h713-tv@*" --no-pager -n 4 | cut -c1-200; dmesg | grep "hdmi:" | tail -3 | cut -c1-200
$B dump cap | grep -E "0x06940928|0x06940968"; lsof /dev/video1 2>/dev/null | head -4; fuser -v /dev/video1 2>&1 | head -4
echo "=== end"
