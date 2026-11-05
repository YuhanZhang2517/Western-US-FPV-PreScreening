"""00 - Optional check: rebuild the four processed ERA5 grids from the raw GRIB1 files and compare them.

Restores the raw-to-grid step of the original notebooks (WUS_reservoirs_solar, WUS_reservoirs_evaporation,
Ice_cover_WUS, WUS_reservoirs_wind). Does not change the grids that 02 uses. Raw files are read in place.
  SSRD: sum of hourly accumulations per year, mean of 2020-2024 (J m-2 yr-1)
  PEV:  the same, multiplied by -1 (m yr-1)
  lake ice depth: maximum over 2020-2024 (m);  10 m wind: maximum of hypot(u, v) over 2020-2024 (m s-1)
Usage: python code/00_era5_rebuild_check.py --era5-root DIR [--run-id ID]
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fpv_config as C  # noqa: E402
import fpv_utils as U   # noqa: E402

NI, NJ = 93, 73
YEARS = range(2020, 2025)
TOLERANCE = 1e-5


def ibm32(b):
    sign = -1.0 if b[0] & 0x80 else 1.0
    return sign * int.from_bytes(b[1:4], "big") * 16.0 ** ((b[0] & 0x7F) - 70)


def messages(path):
    """Yield (valid time, field) from a GRIB1 simple-packing file with 16-bit values and no bitmap."""
    data = memoryview(np.memmap(path, dtype=np.uint8, mode="r"))
    pos = 0
    while pos < len(data):
        if bytes(data[pos:pos + 4]) != b"GRIB" or data[pos + 7] != 1:
            raise ValueError(f"not GRIB1 at byte {pos} of {path}")
        total = int.from_bytes(data[pos + 4:pos + 7], "big")
        p = pos + 8
        l1 = int.from_bytes(data[p:p + 3], "big")
        s1 = bytes(data[p:p + l1])
        decimal = int.from_bytes(s1[26:28], "big")
        decimal = -(decimal & 0x7FFF) if decimal & 0x8000 else decimal
        ref = dt.datetime((s1[24] - 1) * 100 + s1[12], s1[13], s1[14], s1[15], s1[16])
        valid = ref + dt.timedelta(hours=s1[19] if s1[20] == 4 else s1[18])
        if not s1[7] & 0x80 or s1[7] & 0x40:
            raise ValueError("unexpected GDS or bitmap flag")
        p += l1
        p += int.from_bytes(data[p:p + 3], "big")
        l4 = int.from_bytes(data[p:p + 3], "big")
        s4 = data[p:p + l4]
        binary = int.from_bytes(s4[4:6], "big")
        binary = -(binary & 0x7FFF) if binary & 0x8000 else binary
        if s4[10] != 16 or s4[3] & 0xF0:
            raise ValueError("unexpected packing")
        x = np.frombuffer(s4[11:11 + 2 * NI * NJ], dtype=">u2").astype(np.float64)
        yield valid, ((ibm32(bytes(s4[6:10])) + x * 2.0 ** binary) / 10.0 ** decimal).reshape(NJ, NI)
        pos += total


def annual_mean(root, pattern, sign=1.0):
    totals = []
    for y in YEARS:
        t = np.zeros((NJ, NI))
        for _, f in messages(root / pattern.format(y)):
            t += f
        totals.append(sign * t)
    return np.mean(totals, axis=0)


def maximum(root, pattern):
    m = np.full((NJ, NI), -np.inf)
    for y in YEARS:
        for _, f in messages(root / pattern.format(y)):
            np.maximum(m, f, out=m)
    return m


def max_wind(root):
    m = np.zeros((NJ, NI))
    for y in YEARS:
        for (tu, u), (tv, v) in zip(messages(root / f"WUS_wind/10m_u_component_of_wind_{y}.grib"),
                                    messages(root / f"WUS_wind/10m_v_component_of_wind_{y}.grib")):
            if tu != tv:
                raise ValueError("u and v times differ")
            np.maximum(m, np.hypot(u, v), out=m)
    return m


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--era5-root", type=Path, required=True)
    ap.add_argument("--run-id", default=C.RUN_ID)
    args = ap.parse_args()
    U.install_write_guard()
    out = U.stage_dir(args.run_id, 0)
    log = U.get_logger(out, "00_era5_check")
    r = args.era5_root
    rebuilt = {"solar_Jm2": annual_mean(r, "WUS_surface_solar_radiation/surface_solar_radiation_downwards_{}.grib"),
               "evap_m_per_yr": annual_mean(r, "evaporation_ERA5/Potential evaporation_{}.grib", -1.0),
               "ice_m": maximum(r, "Ice_Cover/lake_ice_depth_{}.grib"), "wind_ms": max_wind(r)}
    rows = []
    for name, (path, layer, col) in C.ERA5_GRIDS.items():
        g = gpd.read_file(U.require(path), layer=layer)
        j = np.rint((49.0 - g["latitude"].to_numpy(float)) / 0.25).astype(int)
        i = np.rint((g["longitude"].to_numpy(float) + 125.0) / 0.25).astype(int)
        hist, new = g[col].to_numpy(float), rebuilt[name][j, i]
        rel = np.abs(new - hist) / np.maximum(np.abs(hist), 1e-12)
        rows.append({"grid": name, "cells": len(hist), "max_abs_difference": float(np.abs(new - hist).max()),
                     "max_relative_difference": float(rel.max())})
    t = pd.DataFrame(rows)
    t.to_csv(out / "era5_raw_vs_processed.csv", index=False)
    log.info(t.to_string(index=False))
    if (t["max_relative_difference"] > TOLERANCE).any():
        raise RuntimeError("rebuilt ERA5 grids differ from the processed grids")
    U.write_manifest(out, "00_era5_rebuild_check.py", [p for p, _, _ in C.ERA5_GRIDS.values()],
                     {"years": list(YEARS), "tolerance": TOLERANCE}, ["Raw GRIB files were read in place."])
    log.info("done")


if __name__ == "__main__":
    main()
