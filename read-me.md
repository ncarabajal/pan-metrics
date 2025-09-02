# PAN Metrics

Collector → Postgres → FastAPI → React (Vite/nginx), all wired with Docker Compose.

- **Collector** talks to Panorama + devices over XML-API and writes a snapshot to JSON/CSV.
- A small **ingester** loads that snapshot into **Postgres**.
- The **API** serves latest device health + details from Postgres at `/api/*`.
- The **Web UI** (React) calls the API (proxied by nginx) and renders a live table.

<p align="center">
  <img alt="PAN Metrics Diagram" src="https://user-images.githubusercontent.com/placeholder/diagram.png" width="640">
</p>

---

## Quick start

```bash
# 1) Clone this repo
git clone https://github.com/ncarabajal/pan-metrics.git
cd pan-metrics

# 2) Create your local env & config (edit with real values)
cp .env.example .env
cp collector/config.example.yaml collector/config.yaml

# 3) Build images
docker compose build

# 4) Bring up Postgres first (wait until healthy)
docker compose up -d db

# 5) Bring up the rest
docker compose up -d api web collector

# 6) Check everything
docker compose ps
curl -s http://localhost:8080/api/health | jq
