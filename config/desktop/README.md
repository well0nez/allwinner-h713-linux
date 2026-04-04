# Desktop Configuration (Optional)

These files provide a working Wayland desktop environment for the HY310 projector.
**This is entirely optional** — you can run headless, use a different compositor,
or configure your own desktop setup.

## What's included

- `labwc.service` — systemd service for auto-starting the Labwc compositor
- `labwc/` — Labwc window manager config (keybinds, menu, autostart)
- `waybar/` — Status bar configuration and styling

## Required packages

```bash
apt install labwc waybar wofi thunar foot swaybg xwayland dbus-x11 wlr-randr
```

## Installation

```bash
# Copy labwc service
cp labwc.service /etc/systemd/system/
systemctl enable labwc

# Copy user configs
mkdir -p ~/.config/labwc ~/.config/waybar
cp labwc/* ~/.config/labwc/
cp waybar/* ~/.config/waybar/

# Make sure the DRM module loads at boot
cp ../modules-load.d/h713_drm.conf /etc/modules-load.d/

# Reboot or start manually
systemctl start labwc
```

## Keybinds

- `Super+Enter` — Terminal (foot)
- `Super+D` — App launcher (wofi)
- `Super+E` — File manager (thunar)
- Right-click desktop — Context menu
