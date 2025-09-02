# PAN Metrics

**Firewalls at a glance.** PAN Metrics collects health and capacity signals from Palo Alto Networks firewalls via the XML API, stores the latest snapshot in Postgres, serves it through a clean FastAPI, and renders it in a lightweight React dashboard (served by nginx). Everything runs with Docker Compose.

<p align="center">
  <em>Collector → Postgres → API → Web UI</em>
</p>

---

## Why this exists

- Firewall “how’s it doing?” checks are scattered across CLI and GUIs.
- We wanted a **single table** of devices with **the latest health** (CPU/mem/swap, sessions, disk, logging service, device cert state/expiry, etc.).
- Built for **local dev first** with Docker; later you can point it at AWS/Nautobot without changing the data model.

---

## Key features

- **Batteries included**: Docker Compose brings up Postgres, API, Collector, and Web UI.
- **Safe schema**: explicit columns for common metrics + room for device-specific extras.
- **Reads only**: Collector uses XML-API; no device config changes.
- **Modern UI**: a compact table that color-codes risk (green/yellow/red) and auto-adds new fields when the API provides them.
- **Config-as-file**: simple YAML to declare Panoramas and credentials.
- **No secrets in git**: `.env` and `collector/config.yaml` stay local.

---

## How it works (high level)


1) Collector fetches a **device list** from Panorama.  
2) For each device it uses a **per-device API key** to run read-only commands:
   - `show system info` (version/model)
   - `show system resources` (CPU/mem/swap)
   - `show session info` (current/max)
   - `show system disk-space files` (mount % used)
   - `request logging-service-forwarding status`
   - `show device-certificate status` (state + expiry)
3) Collector writes a JSON/CSV snapshot, then loads it into **Postgres**.  
4) API serves the **latest snapshot per device**.  
5) Web UI polls the API and displays a color-coded table.

---

## Data you get (per device)

**Inventory & state**
- `hostname`, `serial`, `ip`, `panorama`, `connected`, `ha_state`, `timestamp`

**System facts**
- `pan_os_version`, `model`

**Management plane health**
- `cpu_one_min` (load avg 1-min), `memory_usage` (%), `swap_used` (MiB)

**Session table**
- `session_count`, `session_max`

**Logging Service**
- `logging_service` ("yes"/"no")

**Device certificate**
- `device_certificate` ("yes"/"no"/"") and **`device_cert_exp`** (expiry timestamp)

**Disk usage (per mount, varies by platform)**
- Always includes: `disk_root_pct`, `disk_dev_pct`  
- Common mounts (appear when present):  
  `disk_opt_pancfg_pct`, `disk_opt_panrepo_pct`, `disk_dev_shm_pct`,  
  `disk_cgroup_pct`, `disk_opt_panlogs_pct`,  
  `disk_opt_pancfg_mgmt_ssl_private_pct`, `disk_opt_panraid_ld1_pct`

> Mounts that don’t exist on a box simply show as blank for that device.

---

## Screenshots (placeholders)

- **Dashboard table** – live device health with color coding  
  _add your own screenshots under `docs/` and link them here_

---

## Getting started (short)

```bash
# clone
git clone https://github.com/ncarabajal/pan-metrics.git
cd pan-metrics

# local env + config
cp .env.example .env
cp collector/config.example.yaml collector/config.yaml
# edit the files with your real DB creds and Panorama login

# build & run
docker compose build
docker compose up -d db
docker compose up -d api web collector

# check
docker compose ps

## Project Layout ##

api/                    FastAPI app (serves /api/* from Postgres)
collector/              XML-API polling + JSON/CSV + DB ingest
db/                     SQLAlchemy engine/models/patches
pan-metrics-dashboard/  React (Vite) UI served by nginx
Dockerfile.*            Images for api/collector/web
docker-compose.yml      Orchestration
.env.example            Template env (copy to .env)
collector/config.example.yaml  Template (copy to collector/config.yaml)
curl -s http://localhost:8080/api/health | jq
# open http://localhost:8080

## Notes ##

The collector never uses a Panorama key for device calls; it fetches per-device keys (and caches them) to avoid permission surprises.

Schema is explicit for common fields; additional device-specific data can be carried in an extras JSON blob and merged into API output.

If you add new columns later on an existing DB, run the supplied ALTER TABLE statements (or reset with docker compose down -v).
