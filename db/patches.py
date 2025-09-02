# db/patches.py
from sqlalchemy import text

def ensure_columns(engine) -> None:
    # idempotent column adds (safe to run every startup)
    sql = """
    ALTER TABLE metric_snapshots
      ADD COLUMN IF NOT EXISTS disk_opt_pancfg_pct double precision,
      ADD COLUMN IF NOT EXISTS disk_opt_panrepo_pct double precision,
      ADD COLUMN IF NOT EXISTS disk_dev_shm_pct double precision,
      ADD COLUMN IF NOT EXISTS disk_cgroup_pct double precision,
      ADD COLUMN IF NOT EXISTS disk_opt_panlogs_pct double precision,
      ADD COLUMN IF NOT EXISTS disk_opt_pancfg_mgmt_ssl_private_pct double precision,
      ADD COLUMN IF NOT EXISTS disk_opt_panraid_ld1_pct double precision;
    """
    with engine.begin() as conn:
        conn.execute(text(sql))