# db/models.py
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from db.database import Base

class Device(Base):
    __tablename__ = "devices"
    serial = Column(String(64), primary_key=True)
    hostname = Column(String(128), nullable=False, index=True)
    ip = Column(String(45))
    panorama = Column(String(128))
    model = Column(String(64))
    pan_os_version = Column(String(64))
    snapshots = relationship("MetricSnapshot", back_populates="device", cascade="all, delete-orphan")

class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    collected_at = Column(DateTime, index=True, nullable=False)
    device_id = Column(String(64), ForeignKey("devices.serial", ondelete="CASCADE"), nullable=False)

    connected = Column(String(16))
    ha_state = Column(String(32))

    cpu_one_min = Column(Float)
    memory_usage = Column(Float)
    swap_used = Column(Float)

    session_count = Column(Integer)
    session_max = Column(Integer)

    logging_service = Column(String(16))

    device_certificate = Column(String(16))
    device_cert_exp = Column(DateTime)  # stored in UTC

    # disks
    disk_root_pct = Column(Float)
    disk_dev_pct = Column(Float)
    disk_opt_pancfg_pct = Column(Float)
    disk_opt_panrepo_pct = Column(Float)
    disk_dev_shm_pct = Column(Float)
    disk_cgroup_pct = Column(Float)
    disk_opt_panlogs_pct = Column(Float)
    disk_opt_pancfg_mgmt_ssl_private_pct = Column(Float)
    disk_opt_panraid_ld1_pct = Column(Float)

    device = relationship("Device", back_populates="snapshots")

    __table_args__ = (
        UniqueConstraint("device_id", "collected_at", name="uq_device_ts"),
        Index("ix_device_ts", "device_id", "collected_at"),
    )
