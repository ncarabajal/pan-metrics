import os
from pathlib import Path
import yaml

def load_config():
    candidates = []
    env = os.environ.get("CONFIG_PATH")
    if env:
        candidates.append(Path(env).expanduser())

    here = Path(__file__).resolve().parent
    candidates.extend([
        here / "config.yaml",          # /app/collector/config.yaml
        Path("/app/config.yaml"),      # optional alt path
        Path.cwd() / "config.yaml",    # working dir fallback
    ])

    for p in candidates:
        if p and p.is_file():
            with open(p, "r") as f:
                return yaml.safe_load(f)

    raise FileNotFoundError(
        "config.yaml not found. Tried: " + ", ".join(str(p) for p in candidates)
    )
