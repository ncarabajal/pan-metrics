# api/main.py
from datetime import datetime, timedelta, timezone
from typing import List, Dict
from os import getenv

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.database import Base, engine, SessionLocal
from db.models import Device, MetricSnapshot
from db.patches import ensure_columns

app = FastAPI(
    title="PAN Metrics API",
    version="0.5.1",
    description="Latest firewall-health and trends from Postgres (UTC, ISO Z).",
)

extra_origin = getenv("EXTRA_ORIGIN")
allow = ["http://localhost:5173"]
if extra_origin:
    allow.append(extra_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

@app.on_event("startup")
def _startup():
    # create base tables and ensure any patch columns exist
    Base.metadata.create_all(bind=engine)
    ensure_columns(engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _to_z(dt: datetime | None) -> str | None:
    """Return an ISO-8601 string in UTC with trailing 'Z' (or None)."""
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")

@app.get("/health")
def health(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    last = db.execute(select(func.max(MetricSnapshot.collected_at))).scalar()
    device_count = db.execute(select(func.count(Device.serial))).scalar() or 0
    snap_count = db.execute(select(func.count(MetricSnapshot.id))).scalar() or 0
    return {
        "api_time": _to_z(now),
        "last_snapshot": _to_z(last),
        "devices": device_count,
        "rows": snap_count,
        "source": "postgres",
    }

def _pack(dev: Device, s: MetricSnapshot) -> Dict:
    out: Dict = {
        "hostname": dev.hostname,
        "serial": dev.serial,
        "ip": dev.ip,
        "panorama": dev.panorama,
        "pan_os_version": dev.pan_os_version,
        "model": dev.model,

        "connected": s.connected,
        "ha_state": s.ha_state,

        "cpu_one_min": s.cpu_one_min,
        "memory_usage": s.memory_usage,
        "swap_used": s.swap_used,

        "session_count": s.session_count,
        "session_max": s.session_max,

        "logging_service": s.logging_service,

        "device_certificate": s.device_certificate,
        "device_cert_exp": _to_z(s.device_cert_exp),

        # disks (explicit columns in schema)
        "disk_root_pct": s.disk_root_pct,
        "disk_dev_pct": s.disk_dev_pct,
        "disk_opt_pancfg_pct": getattr(s, "disk_opt_pancfg_pct", None),
        "disk_opt_panrepo_pct": getattr(s, "disk_opt_panrepo_pct", None),
        "disk_dev_shm_pct": getattr(s, "disk_dev_shm_pct", None),
        "disk_cgroup_pct": getattr(s, "disk_cgroup_pct", None),
        "disk_opt_panlogs_pct": getattr(s, "disk_opt_panlogs_pct", None),
        "disk_opt_pancfg_mgmt_ssl_private_pct": getattr(s, "disk_opt_pancfg_mgmt_ssl_private_pct", None),
        "disk_opt_panraid_ld1_pct": getattr(s, "disk_opt_panraid_ld1_pct", None),

        "timestamp": _to_z(s.collected_at),
    }

    # If you're storing dynamic extras (JSON/JSONB) via a patches column,
    # merge those too so the UI auto-picks up any future fields.
    if getattr(s, "extras", None):
        try:
            out.update(s.extras)  # type: ignore[arg-type]
        except Exception:
            pass

    return out

@app.get("/devices")
def list_devices(db: Session = Depends(get_db)) -> List[Dict]:
    latest = (
        select(
            MetricSnapshot.device_id,
            func.max(MetricSnapshot.collected_at).label("last_ts"),
        )
        .group_by(MetricSnapshot.device_id)
        .subquery()
    )
    q = (
        select(Device, MetricSnapshot)
        .join(latest, latest.c.device_id == Device.serial)
        .join(
            MetricSnapshot,
            (MetricSnapshot.device_id == latest.c.device_id)
            & (MetricSnapshot.collected_at == latest.c.last_ts),
        )
        .order_by(Device.hostname)
    )
    rows = db.execute(q).all()
    return [_pack(d, s) for d, s in rows]

@app.get("/devices/{serial}")
def device_detail(serial: str, db: Session = Depends(get_db)) -> Dict:
    dev = db.get(Device, serial)
    if not dev:
        raise HTTPException(404, f"{serial} not found")
    snap = (
        db.query(MetricSnapshot)
        .filter(MetricSnapshot.device_id == serial)
        .order_by(MetricSnapshot.collected_at.desc())
        .limit(1)
        .one_or_none()
    )
    if not snap:
        raise HTTPException(404, f"No snapshots for {serial}")
    return {
        "device": {
            "hostname": dev.hostname,
            "serial": dev.serial,
            "ip": dev.ip,
            "panorama": dev.panorama,
            "pan_os_version": dev.pan_os_version,
            "model": dev.model,
        },
        "latest": _pack(dev, snap),
    }

@app.get("/devices/{serial}/trend")
def device_trend(
    serial: str,
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(
            MetricSnapshot.collected_at,
            MetricSnapshot.cpu_one_min,
            MetricSnapshot.memory_usage,
            MetricSnapshot.session_count,
        )
        .filter(MetricSnapshot.device_id == serial, MetricSnapshot.collected_at >= since)
        .order_by(MetricSnapshot.collected_at.asc())
        .all()
    )
    return [
        {
            "t": _to_z(r[0]),
            "cpu_one_min": r[1],
            "memory_usage": r[2],
            "session_count": r[3],
        }
        for r in rows
    ]
