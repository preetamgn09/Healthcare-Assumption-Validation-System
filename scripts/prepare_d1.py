"""Prepare D1 (BRFSS) from files you have already downloaded.

    python scripts/prepare_d1.py --input-dir /path/to/brfss --out data/interim/d1

Deliberately does NOT download anything. The CDC annual-data page is the only authoritative
source for file locations, and hard-coding URLs I cannot verify from this environment would
be exactly the kind of unchecked assumption this project exists to detect. Download the
annual files yourself from the CDC BRFSS annual data page, drop the ZIPs or `.XPT` files in
one directory, and point this script at it.

What it does:

  1. Reads each SAS Transport file (pandas reads XPT natively — no schema assumptions).
  2. Writes one Parquet file per year, which is what the pipeline will actually read.
  3. Writes `d1_column_inventory.json`: every column present in every year, with dtype,
     missing rate and per-year presence.

Step 3 is the point. The dataset config for D1 must be written from the columns that are
actually there, not from remembered variable names — BRFSS renames items across years (the
diabetes item and the calculated CVD variable are both known to move), and modules rotate
in and out. The inventory turns that from a hazard into an input, and the year-to-year
presence table is itself the ground truth for A3 structural monitoring on this substrate.
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from havm.utils import sha256_file, write_json  # noqa: E402


def iter_sources(input_dir: Path):
    for path in sorted(input_dir.iterdir()):
        if path.suffix.upper() == ".XPT":
            yield path.stem, path, None
        elif path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as zf:
                for member in zf.namelist():
                    if member.upper().endswith(".XPT"):
                        yield Path(member).stem, path, member


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--out", default="data/interim/d1")
    args = ap.parse_args()

    src_dir, out_dir = Path(args.input_dir), Path(args.out)
    if not src_dir.is_dir():
        print(f"{src_dir} is not a directory", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)

    inventory, files = {}, []
    for name, container, member in iter_sources(src_dir):
        print(f"reading {name} ...")
        if member:
            with zipfile.ZipFile(container) as zf, zf.open(member) as fh:
                df = pd.read_sas(fh, format="xport")
        else:
            df = pd.read_sas(container, format="xport")

        target = out_dir / f"{name}.parquet"
        df.to_parquet(target, index=False)
        files.append({"source": str(container), "member": member, "parquet": str(target),
                      "rows": int(len(df)), "columns": int(df.shape[1]),
                      "source_sha256": sha256_file(container)})
        print(f"   {len(df):,} rows x {df.shape[1]} columns -> {target}")

        for col in df.columns:
            entry = inventory.setdefault(str(col), {"years_present": [], "dtypes": set(),
                                                    "missing_rate": {}})
            entry["years_present"].append(name)
            entry["dtypes"].add(str(df[col].dtype))
            entry["missing_rate"][name] = round(float(df[col].isna().mean()), 4)

    for entry in inventory.values():
        entry["dtypes"] = sorted(entry["dtypes"])
        entry["n_years_present"] = len(entry["years_present"])

    n_files = len(files)
    always = [c for c, e in inventory.items() if e["n_years_present"] == n_files]
    sometimes = [c for c, e in inventory.items() if e["n_years_present"] < n_files]

    write_json({"files": files, "n_sources": n_files,
                "columns_present_in_every_year": sorted(always),
                "columns_present_in_some_years": sorted(sometimes),
                "inventory": inventory},
               out_dir / "d1_column_inventory.json")

    print(f"\n{n_files} source files, {len(inventory)} distinct columns")
    print(f"   present in every year: {len(always)}  (candidates for a stable feature set)")
    print(f"   present in some years: {len(sometimes)}  (real A3 structural drift on this "
          f"substrate — do not silently harmonise these away)")
    print(f"\nInventory -> {out_dir / 'd1_column_inventory.json'}")
    print("Next: write configs/d1_brfss.yaml from the columns that are actually present, "
          "confirming each against that year's codebook before it enters the feature list.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
