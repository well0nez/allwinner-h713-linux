# The projector's internal camera

Realtek `0bda:5803` "Generic HD camera", UVC 1.00, on `ehci@4200000` (USB port 1, VBUS over PL3).
One format: **YUYV 4:2:2, 640x480**. Stock uses it for autofocus ([`doku/94`](../../doku/94-fokusmotor-endschalter.md)).

**Connected since 11.09.** The bus always saw it, but there was no driver: `uvcvideo` was not built.
Three switches in the defconfig (`MEDIA_CAMERA_SUPPORT`, `MEDIA_USB_SUPPORT`, `USB_VIDEO_CLASS=m`) -
no driver of our own, no patch, no firmware blob. udev loads the module by itself as soon as it is in
the rootfs (`modroot.e88af5af` or newer).

## Device nodes

| Node | What |
|---|---|
| `/dev/video2` | the picture (`VIDEO_CAPTURE`) |
| `/dev/video3` | **not a second device** - the metadata node of the same camera (`META_CAPTURE`, one timestamp per frame). Standard with `uvcvideo`. |

The numbers depend on probe order (`video0` Cedrus, `video1` HDMI-RX). The safe way to find it:
`grep -l "HD camera" /sys/class/video4linux/*/name`.

## Tools (they run on the device with bare `python3`, no `v4l2-ctl`, no `ffmpeg`)

| Script | What for |
|---|---|
| `camprobe.py DEV` | capabilities, formats, frame sizes |
| `camgrab.py DEV OUTPUT.ppm [WxH] [WARMUP]` | one frame over MMAP streaming, YUYV to PPM; `WARMUP` = frames thrown away for the exposure |
| `camset.py DEV ID [VALUE]` | read or set one V4L2 control (IDs in `analyse/hdmi-seq/camctl.py`) |

```bash
scp camgrab.py root@192.168.8.141:/tmp/
ssh root@192.168.8.141 'python3 /tmp/camgrab.py /dev/video2 /tmp/foto.ppm 640x480 30'
scp root@192.168.8.141:/tmp/foto.ppm . && python3 -c "from PIL import Image; Image.open('foto.ppm').save('foto.png')"
```

## The quirk, measured 11.09.

Straight after loading, the camera delivers **black** (Y about 5, pure noise 3 to 9), even after 90
discarded frames and even with a bright HDMI picture on the wall. As soon as **any control has been
written** (`Exposure Time` was enough), the next frame was correctly exposed (Y about 187). Automatic
exposure runs by itself from then on; manual exposure 313 against 800 changes nothing in the result.
That is why `camgrab.py` writes the exposure back once, unchanged, before it starts the stream.

Example: [`foto-e313.png`](foto-e313.png) - the wall in front of the device, HDMI on.
