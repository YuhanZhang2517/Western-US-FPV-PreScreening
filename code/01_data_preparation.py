"""01 - Regional water-body inventory for the 11 western U.S. states (Pathway A).

Historical sources:
  Roadmap/NID_process.ipynb  cell 9  load NID 'dams', keep 11 western states
                             cell 19 gpd.clip to the dissolved western-state mask
                             cell 25 drop surfaceArea NaN or 0           -> 8,507 NID records
  Roadmap/final_AHP_workflow/scripts/merge_natural_lakes_into_nid.py
                             13 CONFIRMED_NATURAL lakes appended (8 EXCLUDED_POSSIBLE never merged) -> 8,520
  (statement-level replica already verified in scripts/reconstructed/r3_inventory_chain.py)
Environmental sampling and the transmission distance (NID_process cells 13-19, 23) are done in
02_data_processing.py; they do not affect which records are selected here.

Historical treatment kept unchanged: no de-duplication by nidId (122 nidIds repeat on 319 rows; issue
C1/D1, unresolved). 8,520 is a RECORD count, not a verified count of distinct water bodies.

Entry points:
  --entry raw        (default) from nation.gpkg; nidId and federalId are carried for traceability
  --entry processed  from the historical 8,507-row nid_selected.csv (no nidId/federalId; NID selection
                     steps are not re-executed - documented reproducibility entry point)

Outputs (outputs/<run-id>/01_data_preparation/): inventory_8520.gpkg/.csv,
  chain_counts.csv, dropped_by_clip.csv, natural_lakes_merge_log.csv, excluded_possible_matches.csv,
  repeated_nidId_groups.csv, figure1_statistics.csv, run_manifest.json
Usage: python code/01_data_preparation.py [--run-id ID] [--entry raw|processed]
"""
import math
import re
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fpv_config as C  # noqa: E402
import fpv_utils as U   # noqa: E402

_GENERIC_TOKENS = {"lake", "reservoir", "dam", "dike", "pond", "res", "impoundment", "no", "number"}


# ------------------------------------------------------------------ merge-script helpers (verbatim logic)
def normalize_name(value):
    if not isinstance(value, str):
        return ""
    s = value.lower().strip()
    s = re.sub(r"\(.*?\)", " ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(sorted(t for t in s.split() if t and t not in _GENERIC_TOKENS))


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), np.radians(lat2)
    dphi, dlmb = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
    a = np.sin(dphi / 2.0) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dlmb / 2.0) ** 2
    return 2.0 * r * np.arcsin(np.sqrt(a))


def classify_against_nid(name, state, lat, lon, nid):
    """'duplicate' (name+state or <=500 m), 'ambiguous' (500-2000 m), or 'new' (merge script)."""
    nn, st = normalize_name(name), str(state).strip().lower()
    hits = nid.index[(nid["_norm"] == nn) & (nid["_state_norm"] == st)].tolist()
    if nn and hits:
        return "duplicate", f"normalized name+state match: '{nid.at[hits[0], 'name']}'", np.nan
    d = haversine_m(float(lat), float(lon), nid["_lat"].to_numpy(), nid["_lon"].to_numpy())
    j = int(np.nanargmin(d))
    near = f"nearest NID '{nid.at[j, 'name']}' ({nid.at[j, 'state']}) at {d[j] / 1000:.2f} km"
    if d[j] <= C.DUP_DIST_M:
        return "duplicate", near, d[j]
    if d[j] <= C.AMBIG_DIST_M:
        return "ambiguous", near, d[j]
    return "new", near, d[j]


# ------------------------------------------------------------------ NID selection
def western_mask():
    states = gpd.read_file(U.require(C.STATE_SHP))
    west = states[states["NAME"].isin(C.WESTERN_STATES)]
    return west.to_crs(4326).dissolve().buffer(0)


def select_nid_raw(log, counts, out):
    nid = gpd.read_file(U.require(C.NID_FULL_GPKG), layer=C.NID_LAYER)
    counts.append(("NID national inventory (nation.gpkg, layer 'dams')", len(nid), nid["nidId"].nunique(),
                   "NID_process.ipynb cell 7/9"))
    keep = nid[[c for c in C.NID_COLUMNS if c in nid.columns]].copy()
    keep = keep[keep["state"].isin(C.WESTERN_STATES)].copy()
    counts.append(("state attribute in 11 western states", len(keep), keep["nidId"].nunique(), "cell 9"))
    keep = keep.to_crs(4326)
    west = gpd.clip(keep, western_mask())
    dropped = keep.loc[~keep.index.isin(west.index), ["nidId", "federalId", "name", "state", "latitude", "longitude"]]
    dropped.to_csv(out / "dropped_by_clip.csv", index=False)
    counts.append(("inside dissolved western-state polygon (gpd.clip)", len(west), west["nidId"].nunique(), "cell 19"))
    west = west.reset_index(drop=True)
    west["surfaceArea"] = pd.to_numeric(west["surfaceArea"], errors="coerce")
    n_null, n_zero = int(west["surfaceArea"].isna().sum()), int((west["surfaceArea"] == 0).sum())
    sel = west[west["surfaceArea"].notna() & (west["surfaceArea"] > 0)].reset_index(drop=True)
    counts.append((f"surfaceArea present and > 0 (removed: {n_null} missing, {n_zero} zero)", len(sel),
                   sel["nidId"].nunique(), "cell 25"))
    log.info(f"NID chain: {counts[0][1]:,} -> {counts[1][1]:,} -> {counts[2][1]:,} -> {len(sel):,}")
    return sel


def select_nid_processed(log, counts):
    df = pd.read_csv(U.require(C.PROCESSED_ENTRY_8507))
    df = df[["name", "ownerTypeIds", "primaryOwnerTypeId", "surfaceArea", "latitude", "longitude", "state",
             "purposeIds"]].copy()
    df.insert(1, "nidId", np.nan)
    df.insert(2, "federalId", np.nan)
    g = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["longitude"], df["latitude"]), crs=4326)
    counts.append(("PROCESSED ENTRY: historical nid_selected.csv (NID selection not re-executed)", len(g),
                   np.nan, "Roadmap/final_AHP_workflow/input/nid/nid_selected.csv"))
    log.warning("processed-data entry point: NID selection steps NOT re-executed; nidId/federalId unavailable; "
                "geometry rebuilt from the saved latitude/longitude")
    return g


# ------------------------------------------------------------------ natural lakes
def add_natural_lakes(nid, log, out):
    work = pd.DataFrame({"name": nid["name"].values, "state": nid["state"].values})
    work["_norm"] = work["name"].map(normalize_name)
    work["_state_norm"] = work["state"].astype(str).str.strip().str.lower()
    work["_lat"] = pd.to_numeric(nid["latitude"], errors="coerce").to_numpy(dtype=float)
    work["_lon"] = pd.to_numeric(nid["longitude"], errors="coerce").to_numpy(dtype=float)
    src = {f: pd.read_csv(U.require(C.NATURAL_LAKE_SOURCE_DIR / f)) for f in C.TOP30_FILE_ORDER_FOR_LAKES}
    for df in src.values():
        df["_norm"] = df["Name"].map(normalize_name)
    rows, logrows = [], []
    for lake in C.CONFIRMED_NATURAL:
        nn = normalize_name(lake)
        hit = next(((f, df.loc[df.index[df["_norm"] == nn][0]]) for f, df in src.items() if (df["_norm"] == nn).any()),
                   None)
        if hit is None:
            raise RuntimeError(f"confirmed natural lake '{lake}' not found in any natural-lake source file")
        f, r = hit
        lat, lon = float(r["latitude"]), float(r["longitude"])
        verdict, detail, dmin = classify_against_nid(r["Name"], r["state"], lat, lon, work)
        logrows.append({"lake": lake, "source_file": f, "verdict": verdict, "detail": detail,
                        "nearest_nid_distance_m": dmin})
        if verdict == "ambiguous":
            raise RuntimeError(f"ambiguous natural-lake match for {lake}: {detail}")
        if verdict != "new":
            continue
        km2 = float(r["surfaceArea_sqkm"])
        rows.append({"name": r["Name"], "nidId": np.nan, "federalId": np.nan,
                     "ownerTypeIds": r.get("Ownership", np.nan), "primaryOwnerTypeId": r.get("Primary Ownership", np.nan),
                     "surfaceArea": km2 / C.ACRE_TO_SQKM, "latitude": lat, "longitude": lon, "state": r["state"],
                     "purposeIds": np.nan, "surfaceArea_sqkm": km2, "source_dataset": "NHD",
                     "is_natural_water_body": True, "natural_lake_source_file": f})
    pd.DataFrame(logrows).to_csv(out / "natural_lakes_merge_log.csv", index=False)
    pd.DataFrame([{"lake": k, "reason_not_merged": v} for k, v in C.EXCLUDED_POSSIBLE.items()]) \
        .to_csv(out / "excluded_possible_matches.csv", index=False)
    log.info(f"natural lakes: {len(rows)} of {len(C.CONFIRMED_NATURAL)} confirmed lakes appended; "
             f"{len(C.EXCLUDED_POSSIBLE)} 'possible match' lakes excluded (historical decision, unchanged)")
    nat = pd.DataFrame(rows)
    return gpd.GeoDataFrame(nat, geometry=gpd.points_from_xy(nat["longitude"], nat["latitude"]), crs=4326)


# ------------------------------------------------------------------ diagnostics
def figure1_statistics(df, label):
    sa = (pd.to_numeric(df["surfaceArea"], errors="coerce") * C.FIG1_ACRE_TO_M2).dropna()
    sa = sa[sa > 0]
    s = np.sort(sa.values)
    rec = {"population": label, "n_records": len(df), "n_valid_area": len(sa),
           "n_area_gt_10km2": int((sa > C.FIG1_THRESHOLD_M2).sum()),
           "pct_records_gt_10km2": (sa > C.FIG1_THRESHOLD_M2).sum() / len(sa) * 100,
           "pct_area_in_gt_10km2": sa[sa > C.FIG1_THRESHOLD_M2].sum() / s.sum() * 100,
           "total_area_km2": s.sum() / 1e6, "min_m2": s.min(), "median_m2": np.median(s), "max_m2": s.max()}
    for pct in (1, 5, 10):
        n_top = max(1, int(np.ceil(len(s) * pct / 100)))
        rec[f"pct_area_in_top_{pct}pct_records"] = s[-n_top:].sum() / s.sum() * 100
    return rec


def repeated_nid_groups(inv):
    d = inv[inv["nidId"].notna() & inv["nidId"].duplicated(keep=False)]
    if d.empty:
        return pd.DataFrame()
    g = d.groupby("nidId").agg(n_records=("name", "size"), names=("name", lambda s: "; ".join(sorted(set(s)))),
                               state=("state", "first"), distinct_areas=("surfaceArea", "nunique"),
                               area_acres_first=("surfaceArea", "first"),
                               area_acres_sum=("surfaceArea", "sum"))
    g["identical_area_on_every_record"] = g["distinct_areas"] == 1
    return g.reset_index().sort_values("n_records", ascending=False)


def main():
    args = U.parse_args(__doc__.splitlines()[0], entry_option=True)
    U.install_write_guard()
    out = U.stage_dir(args.run_id, 1)
    log = U.get_logger(out, "01_data_preparation")
    log.info(f"Pathway A: regional inventory, 11 western states; entry = {args.entry}")
    counts = []
    nid = select_nid_raw(log, counts, out) if args.entry == "raw" else select_nid_processed(log, counts)
    nid = nid[["name", "nidId", "federalId", "ownerTypeIds", "primaryOwnerTypeId", "surfaceArea", "latitude",
               "longitude", "state", "purposeIds", "geometry"]].copy()
    nid["surfaceArea_sqkm"] = pd.to_numeric(nid["surfaceArea"], errors="coerce") * C.ACRE_TO_SQKM
    nid["source_dataset"] = "NID"
    nid["is_natural_water_body"] = False
    nid["natural_lake_source_file"] = np.nan

    nat = add_natural_lakes(nid, log, out)
    inv = gpd.GeoDataFrame(pd.concat([nid, nat[nid.columns]], ignore_index=True), geometry="geometry", crs=4326)
    inv.insert(0, "record_id", np.arange(1, len(inv) + 1))
    counts.append(("+ confirmed natural lakes (NHD branch, merge script)", len(inv),
                   inv["nidId"].nunique() if args.entry == "raw" else np.nan, "merge_natural_lakes_into_nid.py"))
    log.info(f"final inventory: {len(inv):,} records ({(~inv.is_natural_water_body).sum():,} NID + "
             f"{inv.is_natural_water_body.sum()} natural lakes)")

    pd.DataFrame(counts, columns=["step", "records", "unique_nidId", "source"]).to_csv(out / "chain_counts.csv", index=False)
    inv.to_file(out / "inventory_8520.gpkg", driver="GPKG")
    pd.DataFrame(inv.drop(columns="geometry")).assign(
        geom_lon=inv.geometry.x, geom_lat=inv.geometry.y).to_csv(out / "inventory_8520.csv", index=False)
    rep = repeated_nid_groups(inv)
    rep.to_csv(out / "repeated_nidId_groups.csv", index=False)
    if len(rep):
        log.info(f"repeated nidIds (kept unchanged, issue C1): {len(rep)} ids on {int(rep.n_records.sum())} records; "
                 f"{int(rep.identical_area_on_every_record.sum())} groups carry the same area on every record")
    nid_only = inv[~inv["is_natural_water_body"]]
    pd.DataFrame([figure1_statistics(inv, "8,520 inventory (NID + 13 natural lakes)"),
                  figure1_statistics(nid_only, "8,507 NID records only")]).to_csv(out / "figure1_statistics.csv", index=False)

    inputs = ([C.NID_FULL_GPKG, C.STATE_SHP] if args.entry == "raw" else [C.PROCESSED_ENTRY_8507]) + \
             [C.NATURAL_LAKE_SOURCE_DIR / f for f in C.TOP30_FILE_ORDER_FOR_LAKES]
    U.write_manifest(out, "01_data_preparation.py", inputs,
                     {"entry": args.entry, "western_states": C.WESTERN_STATES, "area_filter": "surfaceArea > 0",
                      "acre_to_sqkm": C.ACRE_TO_SQKM, "confirmed_natural": C.CONFIRMED_NATURAL,
                      "excluded_possible": list(C.EXCLUDED_POSSIBLE), "dedup_by_nidId": False},
                     ["8,520 is a record count; repeated nidIds are kept as in the historical workflow (C1).",
                      "Natural-lake identity/area come from the Top-30 CSVs (historical, circular lineage).",
                      "92,603 (manuscript) vs 92,445 (file): no source for 92,603 found (C7)."])
    log.info("done")


if __name__ == "__main__":
    main()
