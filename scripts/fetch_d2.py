"""Acquire D2 (Diabetes 130-US Hospitals, UCI #296) and verify its provenance.

    python scripts/fetch_d2.py                 # canonical UCI source
    python scripts/fetch_d2.py --source mirror # GitHub mirror (development only)

The canonical source is the UCI ML Repository. A mirror is available because some
sandboxed environments cannot reach archive.ics.uci.edu; a mirror is acceptable for
development ONLY, and the checksum below is what makes it acceptable: any file that
hashes to the recorded value is byte-identical to the copy this project was built on.

Before any result enters the report, re-run with --source uci and confirm the checksum
matches. Until then the registry records provenance_status: MIRROR_UNVERIFIED.
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from havm.utils import load_config, sha256_file  # noqa: E402

UCI_ZIP = "https://archive.ics.uci.edu/static/public/296/diabetes+130-us+hospitals+for+years+1999-2008.zip"
MIRROR_CSV = (
    "https://raw.githubusercontent.com/swengzju/Predicting-Diabetes-Patient-Readmission/"
    "master/diabetic_data.csv"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/d2_diabetes.yaml")
    ap.add_argument("--source", choices=["uci", "mirror"], default="uci")
    args = ap.parse_args()

    cfg = load_config(args.config)
    dest = Path(cfg["dataset"]["raw_file"])
    dest.parent.mkdir(parents=True, exist_ok=True)

    if args.source == "uci":
        zip_path = dest.parent / "uci_296.zip"
        print(f"downloading {UCI_ZIP}")
        urllib.request.urlretrieve(UCI_ZIP, zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            name = next(n for n in zf.namelist() if n.endswith("diabetic_data.csv"))
            dest.write_bytes(zf.read(name))
        print(f"extracted {name} -> {dest}")
    else:
        print(f"downloading MIRROR {MIRROR_CSV}")
        urllib.request.urlretrieve(MIRROR_CSV, dest)

    actual = sha256_file(dest)
    expected = cfg["dataset"]["expected_sha256"]
    print(f"sha256 {actual}")
    if actual != expected:
        print(
            f"CHECKSUM MISMATCH\n  expected {expected}\n  actual   {actual}\n"
            "Do not proceed. Either the source changed or the file is not the one this "
            "project was built against. Investigate before updating the config.",
            file=sys.stderr,
        )
        return 1

    print("checksum OK" + ("" if args.source == "uci" else " (mirror — still MIRROR_UNVERIFIED)"))
    if args.source == "uci":
        print("Update configs/d2_diabetes.yaml: provenance_status -> UCI_VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
