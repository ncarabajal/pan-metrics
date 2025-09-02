# 0) move to project root
cd ~/Desktop/PythonProjects/pan-metrics
source .venv/bin/activate

# 1) run collector for fresh data
python -m collector.metrics_collector

# 2) start API in background
uvicorn api.main:app --port 8000 &   # note trailing &

# 3) start dashboard
cd pan-metrics-dashboard
npm run dev

Bring up services (one by one)
# Database (start first)
docker compose up -d db

# API (wait for db healthy if needed)
docker compose up -d api

# Web (nginx + static site)
docker compose up -d web

# Collector
docker compose up -d collector

Bring up everything
docker compose up -d

Rebuild + restart a single service (when code changed)
# e.g., API changed
docker compose build api
docker compose up -d api
# or in one go:
docker compose up -d --no-deps --build api

Useful helpers
# Status
docker compose ps

# Logs (tail)
docker compose logs -f db
docker compose logs -f api
docker compose logs -f web
docker compose logs -f collector

# Restart a service
docker compose restart api

# Stop a service
docker compose stop collector

# Recreate (if env changed)
docker compose up -d --force-recreate api

You said: