"""Shared utilities: config loading, hashing, and the reproducibility record."""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_config(path: str | Path) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def sha256_obj(obj: Any) -> str:
    """Stable hash of a JSON-serialisable object (used for config and sealed-set hashes)."""
    payload = json.dumps(obj, sort_keys=True, default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or "NOT_A_GIT_REPO"
    except Exception:
        return "UNAVAILABLE"


def environment_record() -> dict:
    """Everything BRIEF §36 requires about the runtime, captured automatically."""
    import numpy, pandas, sklearn, scipy

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": {
            "numpy": numpy.__version__,
            "pandas": pandas.__version__,
            "scikit-learn": sklearn.__version__,
            "scipy": scipy.__version__,
        },
    }


def write_json(obj: Any, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2, default=str)
    return path
