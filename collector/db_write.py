# collector/db_write.py
from __future__ import annotations
import json, re
from datetime import datetime, timezone
from typing import List, Dict, Optional

from sqlalchemy.exc import IntegrityError
from db.database import SessionLocal
from db.models import Device, MetricSnapshot

# PAN-OS "YYYY/MM/DD HH:MM:SS UTC" (sometimes "… GMT")
_PANOS_DT_RE = re.compile(
    r"^(?P<y>\d{4})/(?P<m>\d{2})/(?P<d>\d{2}) (?P<H>\d{2}):(?P<M>\d{2}):(?P<S>\d{2}) (UTC|GMT)$"
)

def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    s = s.strip()
    # allow ISO with optional trailing Z
    if s.endswith("Z"):
        s = s[:-1]
    try:
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except Exception:
        pass
    # PAN-OS "YYYY/MM/DD HH:MM:SS UTC"
    m = _PANOS_DT_RE.match(s + " UTC" if "UTC" not in s and "GMT" not in s else s)
    if m:
        return datetime(
            int(m["y"]), int(m["m"]), int(m["d"]),
            int(m["H"]), int(m["M"]), int(m["S"]),
            tzinfo=timezone.utc,
        )
    return None

def _f(v):
    try:
        return float(v) if v is not None and v != "" else None
    except Exception:
        return None

def write_records_to_db(records: List[Dict]) -> int:
    """Insert a batch of device records; ignore duplicate (device_id, collected_at)."""
    if not records:
        return 0

    ins = 0
    with SessionLocal() as db:
        for d in records:
            serial = d.get("serial") or d.get("hostname")
            if not serial:
                continue

            dev = db.get(Device, serial)
            if not dev:
                dev = Device(
                    serial=serial,
                    hostname=d.get("hostname") or serial,
                    ip=d.get("ip"),
                    panorama=d.get("panorama"),
                    model=d.get("model"),
                    pan_os_version=d.get("pan_os_version"),
                )
                db.add(dev)
            else:
                # update mutable fields
                dev.hostname = d.get("hostname") or dev.hostname
                dev.ip = d.get("ip") or dev.ip
                dev.panorama = d.get("panorama") or dev.panorama
                dev.model = d.get("model") or dev.model
                dev.pan_os_version = d.get("pan_os_version") or dev.pan_os_version

            snap = MetricSnapshot(
                device=dev,
                collected_at=_parse_dt(d.get("timestamp")) or datetime.now(timezone.utc),

                connected=d.get("connected"),
                ha_state=d.get("ha_state"),

                cpu_one_min=_f(d.get("cpu_one_min")),
                memory_usage=_f(d.get("memory_usage")),
                swap_used=_f(d.get("swap_used")),

                session_count=d.get("session_count"),
                session_max=d.get("session_max"),

                logging_service=d.get("logging_service"),

                device_certificate=d.get("device_certificate"),
                device_cert_exp=_parse_dt(d.get("device_cert_exp")),

                # disks (store what we have; None is fine)
                disk_root_pct=_f(d.get("disk_root_pct")),
                disk_dev_pct=_f(d.get("disk_dev_pct")),
                disk_opt_pancfg_pct=_f(d.get("disk_opt_pancfg_pct")),
                disk_opt_panrepo_pct=_f(d.get("disk_opt_panrepo_pct")),
                disk_dev_shm_pct=_f(d.get("disk_dev_shm_pct")),
                disk_cgroup_pct=_f(d.get("disk_cgroup_pct")),
                disk_opt_panlogs_pct=_f(d.get("disk_opt_panlogs_pct")),
                disk_opt_pancfg_mgmt_ssl_private_pct=_f(d.get("disk_opt_pancfg_mgmt_ssl_private_pct")),
                disk_opt_panraid_ld1_pct=_f(d.get("disk_opt_panraid_ld1_pct")),
            )

            db.add(snap)
            try:
                db.commit()
                ins += 1
            except IntegrityError:
                db.rollback()  # duplicate; ignore
    return ins

def write_json_to_db(json_path: str) -> int:
    with open(json_path, "r") as f:
        data = json.load(f)
    if isinstance(data, dict) and "devices" in data:
        data = data["devices"]
    if not isinstance(data, list):
        raise ValueError("Unexpected JSON shape; expected a list of devices.")
    return write_records_to_db(data)

# ---- Compatibility alias (fixes ImportError: write_json) ----
def write_json(json_path: str) -> int:
    """Backward-compatible alias for older entrypoints."""
    return write_json_to_db(json_path)
