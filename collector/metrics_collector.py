#!/usr/bin/env python3
"""
Collect firewall health metrics  →  device_metrics.csv / .json
(… header unchanged …)
"""
# ---- distutils shim for Py ≥ 3.12 – keeps older dependencies happy (unchanged)
# ( … unchanged shim here … )
# ------------------------------------------------------------------------------

import re, yaml, requests, urllib3, xml.etree.ElementTree as ET
from collector.config_loader import load_config
from datetime import datetime, timezone, timedelta  # ← added timedelta
import pandas as pd

from collector import pan_connect, get_devices

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_API_TIMEOUT = 10
DEBUG_XML    = False

# ───────────── low-level helpers ─────────────
def api_get(ip: str, key: str, cmd_xml: str) -> str:
    r = requests.get(
        f"https://{ip}/api/?type=op&cmd={cmd_xml}&key={key}",
        verify=False, timeout=_API_TIMEOUT,
    )
    r.raise_for_status()
    return r.text

def _intval(s: str | None):
    try:
        return int(s) if s and s.lower() != "n/a" else None
    except ValueError:
        return None

# ───────────── regexes ─────────────
_DSK_USE_RE = re.compile(r"(?P<pct>\d+)%$")

# ───────────── XML helpers ─────────────
def _txt(xml: str) -> str:
    return ET.fromstring(xml).findtext(".//result") or ""

# ───────────── device-cert time normalization (NEW) ─────────────
# Accepts 'YYYY/MM/DD HH:MM:SS <TZ>' where TZ can be UTC/GMT/PDT/PST/EDT/…
_CERT_RE = re.compile(
    r"^\s*(?P<y>\d{4})/(?P<m>\d{2})/(?P<d>\d{2}) (?P<H>\d{2}):(?P<M>\d{2}):(?P<S>\d{2})(?: (?P<tz>[A-Za-z]+))?\s*$"
)
_TZ_OFFSETS = {
    "UTC": 0, "GMT": 0,
    "EDT": -4, "EST": -5,
    "CDT": -5, "CST": -6,
    "MDT": -6, "MST": -7,
    "PDT": -7, "PST": -8,
    "AKDT": -8, "AKST": -9,
    "HDT": -9, "HST": -10,
}
def _normalize_cert_ts(s: str | None) -> str:
    """Return ISO-8601 UTC ('...Z') or '' if not parseable."""
    if not s:
        return ""
    s = s.strip()

    # Already ISO?
    try:
        if s.endswith("Z"):
            dt = datetime.fromisoformat(s[:-1]).replace(tzinfo=timezone.utc)
            return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass

    m = _CERT_RE.match(s) or _CERT_RE.match(s + " UTC")
    if not m:
        return ""

    y, mo, d = int(m["y"]), int(m["m"]), int(m["d"])
    H, M, S = int(m["H"]), int(m["M"]), int(m["S"])
    tz_abbr = (m.group("tz") or "UTC").upper()
    off = _TZ_OFFSETS.get(tz_abbr)
    if off is None:
        # Unknown tz → treat as UTC to avoid dropping the value
        dt_utc = datetime(y, mo, d, H, M, S, tzinfo=timezone.utc)
        return dt_utc.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    dt_local = datetime(y, mo, d, H, M, S, tzinfo=timezone(timedelta(hours=off)))
    return dt_local.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")

# ───────────── individual parsers (unchanged) ─────────────
def p_system(xml: str):
    t = ET.fromstring(xml)
    return {"pan_os_version": t.findtext(".//sw-version"),
            "model":          t.findtext(".//model")}

def p_resources(xml: str):
    txt  = _txt(xml)
    mem  = re.search(r"MiB Mem.+?([\d.]+)\s+total.+?([\d.]+)\s+used", txt, re.S)
    cpu  = re.search(r"load average:\s*([\d.]+),", txt)
    swap = re.search(r"MiB Swap.+?([\d.]+)\s+used", txt, re.S)
    return {
        "cpu_one_min":  cpu.group(1) if cpu else None,
        "memory_usage": (round(float(mem.group(2)) / float(mem.group(1)) * 100, 2)
                         if mem else None),
        "swap_used":    float(swap.group(1)) if swap else None,
    }

def p_session(xml: str):
    res = ET.fromstring(xml).find(".//result")
    cur = res.findtext("num-active") or res.findtext("active")
    mxx = (res.findtext("num-max") or res.findtext("max")
           or res.findtext("limit") or res.findtext("session-limit"))
    return {"session_count": _intval(cur), "session_max": _intval(mxx)}

def p_disk_files(xml: str):
    raw = _txt(xml)
    if DEBUG_XML:
        print("\n[DISK RAW]\n", raw, "\n")

    out: dict[str, int] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("Filesystem"):
            continue
        parts = line.split()
        if len(parts) < 6:
            continue
        mount = parts[-1]
        m     = _DSK_USE_RE.match(parts[-2])
        if not m:
            continue
        mount_key = "root" if mount == "/" else mount.lstrip("/").replace("/", "_")
        out[f"disk_{mount_key}_pct"] = int(m.group("pct"))
    return out

# logging-service status
_CONN_STATUS_PATH = ".//conn-status"
def p_logging(xml: str):
    tree = ET.fromstring(xml)
    for node in tree.findall(_CONN_STATUS_PATH):
        if re.search(r"\bActive\b", (node.text or ""), flags=re.I):
            return {"logging_service": "yes"}
    summary_msg = (tree.findtext(".//ConnStatus/msg") or "").lower()
    if "established" in summary_msg:
        return {"logging_service": "yes"}
    return {"logging_service": "no"}

# device-certificate status  ← UPDATED to normalize the expiry string
def p_device_cert(xml: str):
    tree = ET.fromstring(xml)
    cert = tree.find(".//device-certificate")
    if cert is None:
        return {"device_certificate": "", "device_cert_exp": ""}
    validity = (cert.findtext("validity") or "").strip().lower()
    status   = (cert.findtext("status") or "").strip().lower()
    exp_raw  = cert.findtext("not_valid_after") or ""
    exp_iso  = _normalize_cert_ts(exp_raw)  # ← normalize to ISO UTC
    is_valid = (validity == "valid") or ("success" in status)
    if is_valid and exp_iso:
        return {"device_certificate": "yes", "device_cert_exp": exp_iso}
    else:
        # still include the (normalized-or-empty) value for visibility
        return {"device_certificate": "no" if cert is not None else "", "device_cert_exp": exp_iso}

# ───────────── per-device collector ─────────────
_firewall_keys: dict[str, str] = {}

def fw_key(ip: str, user: str, pw: str) -> str | None:
    if ip in _firewall_keys:
        return _firewall_keys[ip]
    try:
        key = pan_connect.get_api_key(ip, user, pw)
        _firewall_keys[ip] = key
        return key
    except Exception as e:
        print(f"[!] keygen {ip} – {e}")
        return None

def collect(dev: dict, creds: tuple[str, str]):
    """Always use a per-device key; never reuse Panorama key for device calls."""
    user, pw = creds
    row = {k: dev.get(k, "") for k in
           ("hostname", "serial", "ip", "connected", "ha_state", "panorama")}
    row |= {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pan_os_version": None, "model": None,
        "cpu_one_min": None, "memory_usage": None, "swap_used": None,
        "session_count": None, "session_max": None,
        "logging_service": "no",
        "device_certificate": "",
        "device_cert_exp": "",
        # disk_*_pct added below
    }
    ip = row["ip"]
    if not ip:
        return row

    api_key = fw_key(ip, user, pw)   # ← per-device key only
    if not api_key:
        print(f"[API] skip {ip} – no valid key")
        return row

    def _api(cmd):
        return api_get(ip, api_key, cmd)

    try:
        row |= p_session(_api("<show><session><info></info></session></show>"))
    except Exception as e:
        print(f"[API] session {ip} – {e}")

    try:
        row |= p_system(_api("<show><system><info></info></system></show>"))
    except Exception as e:
        print(f"[API] sys-info {ip} – {e}")

    try:
        row |= p_resources(_api("<show><system><resources></resources></system></show>"))
    except Exception as e:
        print(f"[API] resources {ip} – {e}")

    try:
        row |= p_disk_files(
            _api("<show><system><disk-space><files></files></disk-space></system></show>")
        )
    except Exception as e:
        print(f"[API] disk-files {ip} – {e}")

    try:
        row |= p_logging(
            _api("<request><logging-service-forwarding><status></status></logging-service-forwarding></request>")
        )
    except Exception as e:
        print(f"[API] logging-service {ip} – {e}")

    try:
        row |= p_device_cert(
            _api("<show><device-certificate><status></status></device-certificate></show>")
        )
    except Exception as e:
        print(f"[API] device-cert {ip} – {e}")

    return row

# ───────────── main ─────────────
def main():
    cfg = load_config()
    user, pw = cfg["credentials"].values()

    devices  : list[dict] = []

    # Use Panorama ONLY to fetch inventory; do not reuse its key for device calls
    for p in cfg["panoramas"]:
        try:
            pano_key = pan_connect.get_api_key(p["ip"], user, pw)
            for d in get_devices.fetch_managed_devices(p["ip"], pano_key):
                d["panorama"] = p["name"]
                devices.append(d)
        except Exception as e:
            print(f"[!] panorama {p['name']} – {e}")

    rows = [collect(d, (user, pw)) for d in devices]   # no pano_key passed

    df = pd.DataFrame(rows)
    df.to_csv("device_metrics.csv", index=False)
    df.to_json("device_metrics.json", orient="records", indent=2)
    print(f"✅ device_metrics.csv / .json written – {len(df)} devices")

if __name__ == "__main__":
    main()
