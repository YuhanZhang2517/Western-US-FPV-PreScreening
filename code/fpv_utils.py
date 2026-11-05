"""Shared, non-scientific helpers: write guard, run folders, logging, hashing, manifests."""
import argparse
import datetime as dt
import hashlib
import json
import logging
import platform
import sys
from importlib import metadata
from pathlib import Path

import fpv_config as C


def install_write_guard():
    """Refuse writes outside this repository (write_guard.py)."""
    import write_guard  # noqa: F401  (installs a CPython audit hook on import)
    assert getattr(sys, "_write_guard_installed", False)


def parse_args(description, entry_option=False):
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--run-id", default=C.RUN_ID,
                    help="output folder name under outputs/final_organized/ (default: %(default)s)")
    if entry_option:
        ap.add_argument("--entry", choices=["raw", "processed"], default="raw",
                        help="raw = start from nation.gpkg (default); processed = start from the historical "
                             "8,507-row nid_selected.csv (documented reproducibility entry point; no nidId)")
    return ap.parse_args()


def stage_dir(run_id, stage, create=True):
    d = C.OUTPUT_ROOT / run_id / C.STAGE_DIRS[stage]
    if create:
        if d.exists() and any(d.iterdir()):
            sys.exit(f"refusing to overwrite existing outputs in {d}; choose a new --run-id")
        d.mkdir(parents=True, exist_ok=True)
    elif not d.exists():
        sys.exit(f"required upstream stage folder missing: {d} (run the earlier script with --run-id {run_id})")
    return d


def get_logger(out_dir, name):
    log = logging.getLogger(name)
    log.setLevel(logging.INFO)
    log.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    for h in (logging.StreamHandler(sys.stdout), logging.FileHandler(out_dir / f"{name}.log", mode="x")):
        h.setFormatter(fmt)
        log.addHandler(h)
    return log


def sha256(path, n=None):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:n] if n else h.hexdigest()


def require(path):
    path = Path(path)
    if not path.exists():
        sys.exit(f"missing input: {path}\n  See "
                 f"documentation/DATA_SOURCES.md for how to obtain this file.")
    return path


PACKAGES = ["numpy", "pandas", "scipy", "geopandas", "shapely", "pyproj", "pyogrio", "xarray", "rioxarray",
            "openpyxl"]


def software_versions():
    v = {"python": platform.python_version()}
    for p in PACKAGES:
        try:
            v[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            v[p] = "not installed"
    return v


def write_manifest(out_dir, script, inputs, parameters, notes=None):
    """Record inputs (with hashes), outputs (with hashes), parameters and software versions."""
    out_dir = Path(out_dir)
    outputs = sorted(p for p in out_dir.iterdir() if p.is_file() and p.name != "run_manifest.json")
    man = {
        "script": script,
        "finished": dt.datetime.now().isoformat(timespec="seconds"),
        "workspace_relative": True,
        "inputs": {str(Path(p).relative_to(C.WORKSPACE)): sha256(p) for p in inputs},
        "outputs": {p.name: sha256(p) for p in outputs},
        "parameters": parameters,
        "software": software_versions(),
        "notes": notes or [],
    }
    with open(out_dir / "run_manifest.json", "x") as f:
        json.dump(man, f, indent=2, default=str)
    return man
