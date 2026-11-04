// SPDX-License-Identifier: GPL-3.0-only
//! The remote, as h713-settings' input.c reads it: the Bluetooth remote (1d5a:c081) and the IR receiver (`sunxi-ir`),
//! found by sysfs and held alone (EVIOCGRAB) while the page is open, so nothing below it sees a key. Power is handed to
//! h713-power the way h713-keys does with its launcher open: the remote let go, then the datagram `down`.

use std::fs::{File, OpenOptions};
use std::io::{self, Read};
use std::os::fd::AsRawFd;
use std::os::unix::fs::OpenOptionsExt;
use std::os::unix::net::UnixDatagram;
use std::path::{Path, PathBuf};
use std::sync::mpsc::Sender;
use std::sync::Arc;

use crate::app::{Event, Key, Remote};
use crate::hotkeys::Hotkeys;

/// _IOW('E', 0x90, int)
const EVIOCGRAB: libc::c_ulong = 0x4004_4590;
const EV_KEY: u16 = 1;
/// struct input_event on a 64-bit kernel: struct timeval (16), type, code (u16 each), value (i32).
const EVENT_SIZE: usize = 24;

pub const POWER_SOCKET: &str = "/run/h713-power.sock";

/// A key of the kernel's names to the page's (docs/tools/h713-keys.md); a release is no key, nor a repeat of any but
/// volume and focus.
pub fn map(code: u16, value: i32) -> Option<Key> {
    // volume and focus go on while the key is held (h713-keys), the rest counts on the press
    let held = match code {
        115 => Some(Key::VolumeUp),
        114 => Some(Key::VolumeDown),
        62 => Some(Key::FocusUp),   // KEY_F4, the remote's focus keys
        63 => Some(Key::FocusDown), // KEY_F5
        _ => None,
    };
    if held.is_some() && value != 0 {
        return held;
    }
    if value != 1 {
        return None;
    }
    match code {
        113 => Some(Key::Mute),
        // KEY_ENTER (OK since 70-h713-remote.rules), KEY_OK, KEY_SELECT, BTN_LEFT (the remote's mouse mode)
        28 | 352 | 353 | 0x110 => Some(Key::Ok),
        158 => Some(Key::Back),
        172 => Some(Key::Home),
        116 => Some(Key::Power),
        _ => None,
    }
}

fn first_line(p: &Path) -> String {
    std::fs::read_to_string(p).map(|s| s.lines().next().unwrap_or("").to_string()).unwrap_or_default()
}

/// The event nodes of the stock remote under `sys`/class/input, as paths under `dev`.
pub fn discover(sys: &Path, dev: &Path) -> Vec<PathBuf> {
    let Ok(dir) = std::fs::read_dir(sys.join("class/input")) else { return Vec::new() };
    let mut found: Vec<PathBuf> = dir
        .flatten()
        .filter_map(|e| {
            let name = e.file_name().to_string_lossy().into_owned();
            let d = e.path().join("device");
            let ble = first_line(&d.join("id/vendor")) == "1d5a" && first_line(&d.join("id/product")) == "c081";
            let ir = first_line(&d.join("name")) == "sunxi-ir";
            (name.starts_with("event") && (ble || ir)).then(|| dev.join(name))
        })
        .collect();
    found.sort();
    found
}

pub struct Evdev {
    files: Arc<Vec<File>>,
    grabbed: bool,
    power_socket: PathBuf,
    hotkeys: Hotkeys,
}

impl Evdev {
    /// The remote's devices, held. `H713_AIRPLAY_PAGE_INPUT` (a comma-separated list of files, the tests' FIFOs) stands
    /// for them, not held; `H713_AIRPLAY_PAGE_POWER` for h713-power's socket.
    pub fn open() -> io::Result<Evdev> {
        let power_socket = std::env::var_os("H713_AIRPLAY_PAGE_POWER").map_or_else(|| POWER_SOCKET.into(), PathBuf::from);
        if let Some(list) = std::env::var("H713_AIRPLAY_PAGE_INPUT").ok().filter(|l| !l.is_empty()) {
            // read-write: a FIFO without a writer reports POLLHUP for ever (input.c)
            let files = list.split(',').map(|p| OpenOptions::new().read(true).write(true).open(p)).collect::<io::Result<_>>()?;
            return Ok(Evdev { files: Arc::new(files), grabbed: false, power_socket, hotkeys: Hotkeys::from_env() });
        }
        let nodes = discover(Path::new("/sys"), Path::new("/dev/input"));
        let files: Vec<File> = nodes
            .iter()
            .filter_map(|p| OpenOptions::new().read(true).custom_flags(libc::O_NONBLOCK).open(p).ok())
            .collect();
        if files.is_empty() {
            return Err(io::Error::new(io::ErrorKind::NotFound, "no remote to hold"));
        }
        for f in &files {
            // SAFETY: EVIOCGRAB takes an int by value on an open evdev descriptor.
            if unsafe { libc::ioctl(f.as_raw_fd(), EVIOCGRAB, 1 as libc::c_int) } != 0 {
                return Err(io::Error::new(io::Error::last_os_error().kind(), "the remote's device cannot be held"));
            }
        }
        Ok(Evdev { files: Arc::new(files), grabbed: true, power_socket, hotkeys: Hotkeys::from_env() })
    }

    /// Devices already open (tests: pipes), not held.
    pub fn over(files: Vec<File>, power_socket: PathBuf) -> Evdev {
        Evdev { files: Arc::new(files), grabbed: false, power_socket, hotkeys: Hotkeys::from_env() }
    }

    /// A thread that turns the devices' key presses into [`Event::Key`].
    pub fn start(&mut self, events: Sender<Event>) {
        self.hotkeys.report_to(events.clone());
        let files = Arc::clone(&self.files);
        std::thread::spawn(move || {
            let mut fds: Vec<libc::pollfd> =
                files.iter().map(|f| libc::pollfd { fd: f.as_raw_fd(), events: libc::POLLIN, revents: 0 }).collect();
            loop {
                // SAFETY: pollfds of descriptors `files` keeps open for this thread's life.
                if unsafe { libc::poll(fds.as_mut_ptr(), fds.len() as libc::nfds_t, -1) } < 0 {
                    if io::Error::last_os_error().kind() == io::ErrorKind::Interrupted {
                        continue;
                    }
                    return;
                }
                for (i, p) in fds.iter_mut().enumerate() {
                    let hung = p.revents & libc::POLLHUP != 0 && p.revents & libc::POLLIN == 0;
                    if hung || p.revents & (libc::POLLERR | libc::POLLNVAL) != 0 {
                        p.fd = -1; // a device that went (the Bluetooth remote asleep): poll no longer looks at it
                    }
                    if p.revents & libc::POLLIN == 0 {
                        continue;
                    }
                    let mut ev = [0u8; EVENT_SIZE];
                    if (&files[i]).read_exact(&mut ev).is_err() {
                        continue;
                    }
                    let kind = u16::from_ne_bytes([ev[16], ev[17]]);
                    let code = u16::from_ne_bytes([ev[18], ev[19]]);
                    let value = i32::from_ne_bytes([ev[20], ev[21], ev[22], ev[23]]);
                    if let Some(k) = map(code, value).filter(|_| kind == EV_KEY) {
                        if events.send(Event::Key(k)).is_err() {
                            return;
                        }
                    }
                }
            }
        });
    }
}

impl Remote for Evdev {
    fn release(&mut self) {
        if !self.grabbed {
            return;
        }
        for f in self.files.iter() {
            // SAFETY: as in `open`.
            unsafe { libc::ioctl(f.as_raw_fd(), EVIOCGRAB, 0 as libc::c_int) };
        }
        self.grabbed = false;
    }

    fn hotkey(&mut self, key: Key) {
        self.hotkeys.key(key);
    }

    fn reaped(&mut self) {
        self.hotkeys.reaped();
    }

    fn power(&mut self) {
        let sent = UnixDatagram::unbound().and_then(|s| s.send_to(b"down", &self.power_socket));
        if let Err(e) = sent {
            eprintln!("h713-airplay page: h713-power does not answer ({e}) - the Power press is lost");
        }
    }
}
