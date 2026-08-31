import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pytest  # noqa: E402

from havm.utils import load_config  # noqa: E402

CONFIG = ROOT / "configs" / "d2_diabetes.yaml"


@pytest.fixture(scope="session")
def cfg():
    c = load_config(CONFIG)
    c["dataset"]["raw_file"] = str(ROOT / c["dataset"]["raw_file"])
    return c


@pytest.fixture(scope="session")
def splits(cfg):
    """Real-data fixture. Skipped rather than faked when the raw file is absent."""
    if not Path(cfg["dataset"]["raw_file"]).exists():
        pytest.skip("raw D2 file not present — run scripts/fetch_d2.py first")
    from havm.datasets.d2 import build_splits

    return build_splits(cfg)
