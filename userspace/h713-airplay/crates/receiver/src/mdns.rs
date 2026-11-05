// SPDX-License-Identifier: GPL-3.0-only
//! The mDNS responder of its own (mdns-sd, no avahi on the device): `<MAC>@<name>._raop._tcp` and
//! `<name>._airplay._tcp`, IPv4 only, on every interface with an address (or `config.interfaces`).
//!
//! mdns-sd would look for new interfaces every 5 s; that timer is switched off, and a netlink notifier
//! (blocked in recv while nothing changes) switches it on for a few seconds after each address change.

use crate::info;
use crate::shared::Shared;
use mdns_sd::{IfKind, ServiceDaemon, ServiceInfo};
use std::sync::Arc;
use std::time::Duration;

const SETTLE: Duration = Duration::from_secs(3);

fn host_name(name: &str) -> String {
    let host = std::fs::read_to_string("/etc/hostname").map(|s| s.trim().to_string()).unwrap_or_default();
    let base = if host.is_empty() { name.to_string() } else { host };
    let clean: String = base.chars().map(|c| if c.is_ascii_alphanumeric() || c == '-' { c } else { '-' }).collect();
    format!("{clean}.local.")
}

fn service(ty: &str, instance: &str, host: &str, port: u16, txt: &[(&'static str, String)]) -> mdns_sd::Result<ServiceInfo> {
    let props: Vec<(&str, &str)> = txt.iter().map(|(k, v)| (*k, v.as_str())).collect();
    Ok(ServiceInfo::new(ty, instance, host, "", port, &props[..])?.enable_addr_auto())
}

fn publish(sh: &Shared) -> mdns_sd::Result<ServiceDaemon> {
    let daemon = ServiceDaemon::new()?;
    daemon.set_ip_check_interval(0)?;
    daemon.disable_interface(vec![IfKind::IPv6, IfKind::LoopbackV4, IfKind::LoopbackV6])?;
    if !sh.config.interfaces.is_empty() {
        daemon.disable_interface(IfKind::All)?;
        daemon.enable_interface(sh.config.interfaces.iter().map(|n| IfKind::Name(n.clone())).collect::<Vec<_>>())?;
    }
    let host = host_name(&sh.config.name);
    let port = sh.ports.rtsp;
    let raop = format!("{}@{}", sh.identity.raop_prefix(), sh.config.name);
    daemon.register(service("_raop._tcp.local.", &raop, &host, port, &info::raop_txt(sh))?)?;
    daemon.register(service("_airplay._tcp.local.", &sh.config.name, &host, port, &info::airplay_txt(sh))?)?;
    Ok(daemon)
}

fn follow_interfaces(daemon: &ServiceDaemon) {
    let Ok(mut notifier) = if_addrs::IfChangeNotifier::new() else {
        eprintln!("h713-airplay: mdns: no interface notifier, checking every 5 s instead");
        let _ = daemon.set_ip_check_interval(5);
        return;
    };
    while notifier.wait(None).is_ok() {
        let _ = daemon.set_ip_check_interval(1);
        while notifier.wait(Some(SETTLE)).is_ok() {}
        let _ = daemon.set_ip_check_interval(0);
    }
}

/// Publishes both services and keeps them on every interface that comes and goes (a thread of its own).
pub fn start(sh: Arc<Shared>) {
    let daemon = match publish(&sh) {
        Ok(d) => d,
        Err(e) => {
            eprintln!("h713-airplay: mdns: {e}");
            *sh.mdns.lock().unwrap() = format!("error {e}");
            return;
        }
    };
    *sh.mdns.lock().unwrap() = "published".into();
    eprintln!("h713-airplay: mdns published {} on {:?}", sh.config.name, crate::net::addrs(&sh.config.interfaces));
    let spawned = std::thread::Builder::new().name("mdns-if".into()).spawn(move || follow_interfaces(&daemon));
    if let Err(e) = spawned {
        eprintln!("h713-airplay: mdns interface thread: {e}");
    }
}
