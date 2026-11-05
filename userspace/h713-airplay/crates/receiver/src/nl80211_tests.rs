// SPDX-License-Identifier: GPL-3.0-only
use super::*;

const FAMILY: u16 = 0x1c;

fn attr(t: u16, v: &[u8]) -> Vec<u8> {
    let mut a = ((4 + v.len()) as u16).to_ne_bytes().to_vec();
    a.extend_from_slice(&t.to_ne_bytes());
    a.extend_from_slice(v);
    a.resize(align4(a.len()), 0);
    a
}

fn message(kind: u16, seq: u32, cmd: u8, attrs: &[Vec<u8>]) -> Vec<u8> {
    let body: Vec<u8> = [cmd, 1, 0, 0].into_iter().chain(attrs.concat()).collect();
    raw(kind, seq, &body)
}

fn raw(kind: u16, seq: u32, body: &[u8]) -> Vec<u8> {
    let mut m = ((HEADER + body.len()) as u32).to_ne_bytes().to_vec();
    m.extend_from_slice(&kind.to_ne_bytes());
    m.extend_from_slice(&2u16.to_ne_bytes());
    m.extend_from_slice(&seq.to_ne_bytes());
    m.extend_from_slice(&0u32.to_ne_bytes());
    m.extend_from_slice(body);
    m
}

fn error(seq: u32, errno: i32) -> Vec<u8> {
    raw(NLMSG_ERROR, seq, &[(-errno).to_ne_bytes().to_vec(), vec![0; 16]].concat())
}

fn iface(name: &str, iftype: u32, ssid: Option<&[u8]>) -> Vec<u8> {
    let mut a = vec![attr(3, &7u32.to_ne_bytes()), attr(NL80211_ATTR_IFNAME, format!("{name}\0").as_bytes())];
    a.push(attr(NL80211_ATTR_IFTYPE, &iftype.to_ne_bytes()));
    if let Some(s) = ssid {
        a.push(attr(NL80211_ATTR_SSID, s));
    }
    message(FAMILY, 2, 7, &a)
}

#[test]
fn the_family_id_comes_from_getfamily_and_a_kernel_without_nl80211_is_none() {
    let answer = message(GENL_ID_CTRL, 1, 1, &[attr(CTRL_ATTR_FAMILY_NAME, b"nl80211\0"), attr(CTRL_ATTR_FAMILY_ID, &FAMILY.to_ne_bytes())]);
    assert!(matches!(family_answer(&answer, 1).unwrap(), Answer::Got(Some(FAMILY))));
    assert!(matches!(family_answer(&answer, 9).unwrap(), Answer::Pending), "another request's answer");
    assert!(matches!(family_answer(&error(1, libc::ENOENT), 1).unwrap(), Answer::Got(None)));
    assert!(family_answer(&error(1, libc::EPERM), 1).is_err());
}

#[test]
fn an_access_point_reports_its_ssid_and_a_station_without_one_is_left_out() {
    let first = [iface("wlan0", 3, Some(b"h713")), iface("wlan1", 2, None), iface("p2p0", 9, Some(b"my net"))].concat();
    let mut got = Vec::new();
    assert!(!dump_part(&first, 2, FAMILY, &mut got).unwrap());
    assert!(dump_part(&raw(NLMSG_DONE, 2, &0i32.to_ne_bytes()), 2, FAMILY, &mut got).unwrap());
    assert_eq!(got[0], Iface { name: "wlan0".into(), iftype: 3, ssid: b"h713".to_vec() });
    assert_eq!((got[1].name.as_str(), got[1].iftype, got[1].ssid.is_empty()), ("wlan1", 2, true));
    assert_eq!(report(got), vec!["h713@wlan0", "my_net@p2p0"]);
}

#[test]
fn malformed_lengths_are_errors_not_panics() {
    let good = iface("wlan0", 3, Some(b"h713"));
    let mut cut = good.clone();
    cut.truncate(good.len() - 3);
    assert!(dump_part(&cut, 2, FAMILY, &mut Vec::new()).is_err(), "message longer than the buffer");
    let mut short_attr = good.clone();
    short_attr[HEADER + GENL_HEADER..HEADER + GENL_HEADER + 2].copy_from_slice(&3u16.to_ne_bytes());
    assert!(dump_part(&short_attr, 2, FAMILY, &mut Vec::new()).is_err(), "attribute shorter than its header");
    let mut long_attr = good.clone();
    long_attr[HEADER + GENL_HEADER..HEADER + GENL_HEADER + 2].copy_from_slice(&200u16.to_ne_bytes());
    assert!(dump_part(&long_attr, 2, FAMILY, &mut Vec::new()).is_err(), "attribute past the message");
    let bad_type = message(FAMILY, 2, 7, &[attr(NL80211_ATTR_IFNAME, b"wlan0\0"), attr(NL80211_ATTR_IFTYPE, &[3])]);
    assert!(dump_part(&bad_type, 2, FAMILY, &mut Vec::new()).is_err(), "a 1-byte iftype");
    assert!(dump_part(&raw(NLMSG_ERROR, 2, &[1, 2]), 2, FAMILY, &mut Vec::new()).is_err(), "short error");
    assert!(dump_part(&error(2, libc::EINVAL), 2, FAMILY, &mut Vec::new()).is_err());
}
