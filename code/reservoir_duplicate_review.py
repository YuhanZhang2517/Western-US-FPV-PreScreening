#!/usr/bin/env python3
"""Standalone duplicate-record review for the western U.S. FPV regional inventory.

Screens records on three fields only: reservoir name, state, water surface area.
Results are SCREENING RESULTS. They do not establish that two records are the same physical
reservoir. No fuzzy or geographic matching is used, and records are never merged because they
share a Dam ID. Coordinates and Dam IDs are reported descriptively and never affect a category.

Categories
  1  Exact duplicate candidates: same normalized name, same state, identical surface area
  2  Possible duplicates: same normalized name and state, different surface area (manual review)
  3  Missing information: name, state or a positive surface area is missing or unrecognized
  4  No duplicate match identified

MANUAL_KEEP: records the author has verified as distinct reservoirs. They stay in Category 1, because
detection is unchanged, but they are never removed. The override runs after detection and representative
selection, and it stops the run if any listed record cannot be matched exactly.

The input inventory and the NID identifier source are read-only. The script writes only its five
outputs, and refuses to run if any of them already exists.

Normally run by 01b_deduplication.py.

Usage: python reservoir_duplicate_review.py --output-dir /some/new/folder [--area-tolerance-rel 0.01]
"""
import argparse
import datetime as dt
import hashlib
import platform
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parent
DEFAULT_INPUT = WORKSPACE / "data/regional/historical_inputs/nid_selected_with_natural_lakes.csv"
DEFAULT_ID_SOURCE = WORKSPACE / "data/regional/nid_identifiers_west.sqlite"

# Column names confirmed by inspecting the input file.
NAME, STATE, AREA = "name", "state", "surfaceArea"       # surfaceArea unit: acres
LAT, LON, SOURCE = "latitude", "longitude", "source_dataset"
REQUIRED = [NAME, STATE, AREA, LAT, LON, SOURCE]
# Attributes counted for representative-record completeness. HAB columns are excluded because
# they are empty for all NID records and so cannot separate candidates.
COMPLETENESS = ["ownerTypeIds", "primaryOwnerTypeId", LAT, LON, "solar_Jm2", "solar_kWhm2", "evap_m_per_yr",
                "ice_m", "wind_ms", "dist_to_grid_m", "purposeIds", "surfaceArea_sqkm", "Capacity_Factor"]
ACRE_TO_KM2 = 0.00404685642      # factor documented in merge_natural_lakes_into_nid.py
NID_ID_PATTERN = re.compile(r"^[A-Z]{2}\d{5}$")
MISSING_TOKENS = {"", "nan", "none", "null", "na", "n/a"}
OUTPUTS = ["duplicate_summary.csv", "duplicate_candidates.csv", "inventory_deduplicated_proposed.csv",
           "duplicate_group_mapping.csv", "DUPLICATE_REVIEW_REPORT.md"]
STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming"}
# MANUAL_KEEP override. Each record below was manually verified by the author on 2026-11-03 as a distinct
# reservoir that only coincidentally shares a name, state and area with another record. To add a record,
# give all fields; a record is matched on Dam ID + name + state + area, then its row and group are validated.
MANUAL_KEEP = [
    {"duplicate_group_id": "E0001", "input_row": 7927, "dam_id": "CA00438", "name": "Crystal Lake",
     "state": "California", "area_acres": 12.0},
    {"duplicate_group_id": "E0002", "input_row": 6566, "dam_id": "CO02239", "name": "Buffalo Creek",
     "state": "Colorado", "area_acres": 25.0},
    {"duplicate_group_id": "E0004", "input_row": 3374, "dam_id": "CO00621", "name": "Reynolds",
     "state": "Colorado", "area_acres": 15.0},
]
MANUAL_KEEP_REASON = "MANUAL_KEEP: author verified as a distinct reservoir (2026-11-03)"
STATE_LOOKUP = {**{k.lower(): v for k, v in STATE_NAMES.items()}, **{v.lower(): v for v in STATE_NAMES.values()}}


def is_missing(value):
    return str(value).strip().lower() in MISSING_TOKENS


def normalize_name(value):
    """Lowercase, trim, standardize punctuation and spaces. Words such as 'dam' or 'lake' are kept."""
    if is_missing(value):
        return ""
    s = unicodedata.normalize("NFKC", str(value)).lower().replace("&", " and ")
    s = re.sub(r"['’`]", "", s)             # O'Neill -> oneill
    s = re.sub(r"[^\w\s]|_", " ", s)             # other punctuation becomes a space
    return " ".join(s.split())


def standardize_state(value):
    """Full state name, or '' when missing or unrecognized."""
    return "" if is_missing(value) else STATE_LOOKUP.get(" ".join(str(value).split()).lower(), "")


def file_fingerprint(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    stat = Path(path).stat()
    return {"path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha256": digest.hexdigest()}


def id_key(name, state, lat, lon, area):
    """Exact-match key. Coordinates use 8 decimals (about 1 mm) because the inventory CSV and the
    GeoPackage can differ in the last floating-point digit."""
    return (name, state, round(float(lat), 8), round(float(lon), 8), float(area))


def load_nid_ids(path):
    """Read identifiers from the NID GeoPackage. immutable=1 stops SQLite creating or changing any file."""
    con = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    try:
        ids = pd.read_sql("SELECT name, state, latitude, longitude, surfaceArea, nidId, otherStructureId, "
                          "isAssociatedStructureId FROM dams", con)
    finally:
        con.close()
    lookup = {}
    for r in ids.itertuples(index=False):
        try:
            key = id_key(r.name, r.state, r.latitude, r.longitude, r.surfaceArea)
        except (TypeError, ValueError):
            continue
        lookup.setdefault(key, []).append((str(r.nidId or "").strip(), r.isAssociatedStructureId, r.otherStructureId))
    return lookup


def attach_ids(df, lookup):
    """Attach Dam IDs by an exact five-field key. Candidates are listed, never guessed between."""
    ids, status, assoc = [], [], []
    for r in df.itertuples():
        row = df.loc[r.Index]
        if row[SOURCE] != "NID":
            ids.append(""), status.append("none: no Dam ID for this source"), assoc.append("")
            continue
        try:
            key = id_key(row[NAME], row[STATE], row[LAT], row[LON], row[AREA])
        except ValueError:
            key = None
        hits = sorted({h[0] for h in lookup.get(key, []) if h[0]})
        ids.append("|".join(hits))
        assoc.append("|".join(sorted({str(h[1]) for h in lookup.get(key, [])})))
        if not hits:
            status.append("none: no exact NID match")
        elif len(hits) > 1:
            status.append("ambiguous: several Dam IDs share this exact key")
        elif NID_ID_PATTERN.match(hits[0]):
            status.append("valid")
        else:
            status.append("invalid format")
    df["source_id"], df["source_id_status"], df["nid_is_associated_structure"] = ids, status, assoc
    return df


def classify(df, tol):
    area = pd.to_numeric(df[AREA], errors="coerce")
    df["area_acres"] = area
    df["standardized_name"] = df[NAME].map(normalize_name)
    df["standardized_state"] = df[STATE].map(standardize_state)
    bad = pd.DataFrame({"name": df["standardized_name"] == "", "state": df["standardized_state"] == "",
                        "surface area": area.isna() | (area <= 0)})
    invalid = bad.any(axis=1)
    df["duplicate_group_id"], df["name_state_group_id"] = "", ""
    df["duplicate_classification"] = "Category 4 - No duplicate match identified"
    df["reason_for_classification"] = "No other record shares this normalized name and state"
    df.loc[invalid, "duplicate_classification"] = "Category 3 - Missing information"
    df.loc[invalid, "reason_for_classification"] = [
        "Missing or unrecognized: " + ", ".join(c for c in bad.columns if bad.at[i, c]) for i in df.index[invalid]]
    v = df[~invalid]
    pair = ["standardized_state", "standardized_name"]
    for n, (_, g) in enumerate(((k, g) for k, g in v.groupby(pair, sort=True) if len(g) > 1), 1):
        df.loc[g.index, "name_state_group_id"] = f"NS{n:04d}"
        areas = g["area_acres"]
        repeated = areas[areas.duplicated(keep=False)].index
        for i in g.index.difference(repeated):
            others = areas.drop(i).unique()
            rel = min(abs(areas[i] - a) / max(areas[i], a) for a in others)
            if tol is None or rel <= tol:
                df.at[i, "duplicate_classification"] = "Category 2 - Possible duplicate, manual review"
                limit = "no tolerance limit set" if tol is None else f"within tolerance {tol:g}"
                df.at[i, "reason_for_classification"] = (
                    f"Same normalized name and state; smallest relative area difference {rel:.4%} ({limit})")
            else:
                df.at[i, "reason_for_classification"] = (
                    f"Same normalized name and state, but area differs by {rel:.4%}, beyond tolerance {tol:g}")
    exact = v[v.duplicated(pair + ["area_acres"], keep=False)]
    for n, (_, g) in enumerate(exact.groupby(pair + ["area_acres"], sort=True), 1):
        df.loc[g.index, "duplicate_group_id"] = f"E{n:04d}"
        df.loc[g.index, "duplicate_classification"] = "Category 1 - Exact duplicate candidate"
        df.loc[g.index, "reason_for_classification"] = "Same normalized name, same state, identical surface area"
    return df


def pick_representatives(df, cols):
    """Rank: valid source ID, then attribute completeness, then original row order."""
    df["representative_record_flag"] = False
    df["representative_input_row"] = df["input_row"]
    df["group_distinct_coordinates"] = ""
    df["group_distinct_source_ids"] = ""
    df["group_attribute_conflicts"] = ""
    id_rank = lambda s: 0 if s == "valid" else (1 if s.startswith("ambiguous") else 2)
    present = [c for c in COMPLETENESS if c in df]
    filled = (~df[present].apply(lambda s: s.map(is_missing))).sum(axis=1)
    for gid, g in df[df["duplicate_group_id"] != ""].groupby("duplicate_group_id"):
        order = sorted(g.index, key=lambda i: (id_rank(df.at[i, "source_id_status"]), -filled[i], df.at[i, "input_row"]))
        rep = order[0]
        df.at[rep, "representative_record_flag"] = True
        df.loc[g.index, "representative_input_row"] = df.at[rep, "input_row"]
        df.loc[g.index, "group_distinct_coordinates"] = str(len(g[[LAT, LON]].drop_duplicates()))
        df.loc[g.index, "group_distinct_source_ids"] = str(len({x for s in g["source_id"] for x in s.split("|") if x}))
        conflicts = [c for c in cols if c != NAME and g[c].nunique() > 1]
        df.loc[g.index, "group_attribute_conflicts"] = "; ".join(conflicts)
    return df


def apply_manual_keep(df):
    """Mark MANUAL_KEEP records as retained. Categories, group IDs and representatives are not changed.

    Stops the run unless each entry matches exactly one Category 1, non-representative record, because
    an unmatched override would silently remove a reservoir the author has said must be kept.
    """
    df["manual_keep_flag"] = False
    df["manual_keep_reason"] = ""
    for k in MANUAL_KEEP:
        hits = df[(df["source_id"] == k["dam_id"]) & (df[NAME].str.strip() == k["name"]) &
                  (df[STATE].str.strip() == k["state"]) & (df["area_acres"] == k["area_acres"])]
        if len(hits) != 1:
            sys.exit(f"MANUAL_KEEP stopped: {len(hits)} records match {k}; expected exactly 1")
        i = hits.index[0]
        found = {"input_row": int(df.at[i, "input_row"]), "duplicate_group_id": df.at[i, "duplicate_group_id"]}
        for field, value in found.items():
            if value != k[field]:
                sys.exit(f"MANUAL_KEEP stopped: {k['dam_id']} has {field} {value!r}, expected {k[field]!r}")
        if not df.at[i, "duplicate_classification"].startswith("Category 1"):
            sys.exit(f"MANUAL_KEEP stopped: {k['dam_id']} is not a Category 1 record; review this override")
        if df.at[i, "representative_record_flag"]:
            sys.exit(f"MANUAL_KEEP stopped: {k['dam_id']} is already the representative; review this override")
        df.at[i, "manual_keep_flag"] = True
        df.at[i, "manual_keep_reason"] = MANUAL_KEEP_REASON
        df.at[i, "representative_input_row"] = df.at[i, "input_row"]    # a distinct reservoir maps to itself
    return df


def table(frame):
    head = "| " + " | ".join(frame.columns) + " |\n|" + "---|" * len(frame.columns) + "\n"
    body = "\n".join("| " + " | ".join(str(x) for x in row) + " |" for row in frame.itertuples(index=False))
    return head + body + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--id-source", type=Path, default=DEFAULT_ID_SOURCE)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--area-tolerance-rel", type=float, default=None,
                    help="optional relative limit for Category 2; default: none, so every same-name, same-state "
                         "record with a different area goes to manual review")
    ap.add_argument("--high-area-km2", type=float, default=10.0, help="reporting threshold only (Figure 1 uses 10)")
    ap.add_argument("--fpv-coverage", type=float, default=0.10, help="coverage ratio, manuscript Sec 2.3.1")
    args = ap.parse_args()

    existing = [n for n in OUTPUTS if (args.output_dir / n).exists()]
    if existing:
        sys.exit(f"refusing to overwrite existing output(s) in {args.output_dir}: {existing}")
    before = {"input": file_fingerprint(args.input), "id_source": file_fingerprint(args.id_source)}

    original = pd.read_csv(args.input, dtype=str, keep_default_na=False, na_filter=False)
    missing_cols = [c for c in REQUIRED if c not in original.columns]
    if missing_cols:
        sys.exit(f"input lacks required column(s): {missing_cols}; columns found: {list(original.columns)}")
    cols = list(original.columns)
    df = original.copy()
    df.insert(0, "input_row", range(1, len(df) + 1))      # 1 = first data row of the input
    df = attach_ids(df, load_nid_ids(args.id_source))
    df = classify(df, args.area_tolerance_rel)
    df = pick_representatives(df, cols)
    df = apply_manual_keep(df)

    is1 = df["duplicate_classification"].str.startswith("Category 1")
    is2 = df["duplicate_classification"].str.startswith("Category 2")
    is3 = df["duplicate_classification"].str.startswith("Category 3")
    is4 = df["duplicate_classification"].str.startswith("Category 4")
    keep = df["manual_keep_flag"]
    remove = is1 & ~df["representative_record_flag"] & ~keep
    df["proposed_action"] = ["remove from proposed inventory (kept in original)" if r else
                             ("retain (MANUAL_KEEP)" if k else "retain") for r, k in zip(remove, keep)]
    kept_groups = df.loc[keep, "duplicate_group_id"]
    kept_acres = df.loc[keep, "area_acres"].sum()
    proposed = original[~remove.values]
    area = df["area_acres"].fillna(0)
    a0, a1 = area.sum(), area[~remove].sum()
    km0, km1 = a0 * ACRE_TO_KM2, a1 * ACRE_TO_KM2
    n_groups = df.loc[is1, "duplicate_group_id"].nunique()

    # ---- outputs
    out = args.output_dir
    extra = ["input_row", "standardized_name", "standardized_state", "duplicate_group_id", "name_state_group_id",
             "duplicate_classification", "representative_record_flag", "manual_keep_flag", "manual_keep_reason",
             "proposed_action", "reason_for_classification", "source_id",
             "source_id_status", "nid_is_associated_structure", "group_distinct_coordinates",
             "group_distinct_source_ids", "group_attribute_conflicts"]
    flagged = df[is1 | is2 | is3].sort_values(["duplicate_classification", "standardized_state", "standardized_name",
                                               "area_acres", "input_row"])
    flagged[extra + cols].to_csv(out / "duplicate_candidates.csv", index=False, mode="x")
    proposed.to_csv(out / "inventory_deduplicated_proposed.csv", index=False, mode="x")
    rep_lookup = df.set_index("input_row")
    mapping = pd.DataFrame({
        "input_row": df["input_row"], "original_name": df[NAME], "original_state": df[STATE],
        "surface_area_acres": df[AREA], "source_id": df["source_id"], "source_id_status": df["source_id_status"],
        "source_dataset": df[SOURCE], "duplicate_classification": df["duplicate_classification"],
        "duplicate_group_id": df["duplicate_group_id"], "name_state_group_id": df["name_state_group_id"],
        "proposed_action": df["proposed_action"], "manual_keep_flag": keep,
        "manual_keep_reason": df["manual_keep_reason"],
        "representative_input_row": df["representative_input_row"],
        "representative_name": df["representative_input_row"].map(rep_lookup[NAME]),
        "representative_source_id": df["representative_input_row"].map(rep_lookup["source_id"])})
    mapping.to_csv(out / "duplicate_group_mapping.csv", index=False, mode="x")

    # ---- validation
    after = {k: file_fingerprint(v["path"]) for k, v in before.items()}
    reread = pd.read_csv(out / "inventory_deduplicated_proposed.csv", dtype=str, keep_default_na=False, na_filter=False)
    reps = df[df["representative_record_flag"]]
    retained_rows = set(df.loc[~remove, "input_row"])
    checks = [
        ("Input inventory unchanged (SHA-256, size, mtime)", before["input"] == after["input"]),
        ("NID identifier source unchanged (SHA-256, size, mtime)", before["id_source"] == after["id_source"]),
        ("Retained rows are identical, value for value, to the input",
         reread.equals(original.loc[~remove.values].reset_index(drop=True))),
        ("Each Category 1 group has exactly one representative",
         (reps.groupby("duplicate_group_id").size() == 1).all() and len(reps) == n_groups),
        ("Every representative is retained", set(reps["input_row"]) <= retained_rows),
        ("Mapping has one row per input record", len(mapping) == len(df) and mapping["input_row"].is_unique),
        ("Every mapped representative exists in the proposed inventory",
         set(mapping["representative_input_row"]) <= retained_rows),
        ("Categories 2, 3 and 4 are all retained", not bool(remove[is2 | is3 | is4].any())),
        ("Original count minus removed equals proposed count", len(df) - int(remove.sum()) == len(proposed)),
        ("Categories sum to the original count", int(is1.sum() + is2.sum() + is3.sum() + is4.sum()) == len(df)),
        ("Every MANUAL_KEEP entry matched one record and is retained",
         int(keep.sum()) == len(MANUAL_KEEP) and set(df.loc[keep, "input_row"]) <= retained_rows),
        ("Original representatives of MANUAL_KEEP groups are retained",
         set(reps.loc[reps["duplicate_group_id"].isin(kept_groups), "input_row"]) <= retained_rows
         and int(reps["duplicate_group_id"].isin(kept_groups).sum()) == kept_groups.nunique()),
        ("Other Category 1 groups each lose all but their representative",
         bool((df[is1 & ~df["duplicate_group_id"].isin(kept_groups) & ~remove].groupby("duplicate_group_id").size() == 1).all())),
        ("No Category 1 group in MANUAL_KEEP loses a record",
         not bool(remove[df["duplicate_group_id"].isin(kept_groups)].any()))]
    all_ok = all(bool(ok) for _, ok in checks)

    # ---- summary
    summary = pd.DataFrame([
        ("Original record count", len(df)),
        ("Exact duplicate candidate groups", n_groups),
        ("Records flagged as exact duplicate candidates", int(is1.sum())),
        ("Category 1 groups kept in full by MANUAL_KEEP", kept_groups.nunique()),
        ("Records kept by MANUAL_KEEP", int(keep.sum())),
        ("Surface area kept by MANUAL_KEEP (acres)", round(kept_acres, 3)),
        ("Records proposed for removal", int(remove.sum())),
        ("Records requiring manual review (Category 2)", int(is2.sum())),
        ("Name-and-state groups with more than one record", df.loc[df["name_state_group_id"] != "", "name_state_group_id"].nunique()),
        ("Missing-information records (Category 3)", int(is3.sum())),
        ("Records with no duplicate match (Category 4)", int(is4.sum())),
        ("Records retained in proposed inventory", len(proposed)),
        ("Original total surface area (acres)", round(a0, 3)),
        ("Proposed total surface area (acres)", round(a1, 3)),
        ("Surface area difference (acres)", round(a0 - a1, 3)),
        ("Original total surface area (km2)", round(km0, 3)),
        ("Proposed total surface area (km2)", round(km1, 3)),
        ("Surface area difference (km2)", round(km0 - km1, 3)),
        ("Surface area difference (percent)", round((a0 - a1) / a0 * 100, 4)),
        (f"Original FPV-covered area at {args.fpv_coverage:.0%} (km2)", round(km0 * args.fpv_coverage, 3)),
        (f"Proposed FPV-covered area at {args.fpv_coverage:.0%} (km2)", round(km1 * args.fpv_coverage, 3)),
        ("All validation checks passed", all_ok)], columns=["metric", "value"])
    summary.to_csv(out / "duplicate_summary.csv", index=False, mode="x")

    # ---- report
    id_counts = df.loc[df["source_id_status"] == "valid", "source_id"].value_counts()
    shared = id_counts[id_counts > 1]
    shared_rows = df["source_id"].isin(shared.index)
    g1 = df[is1].sort_values(["duplicate_group_id", "input_row"]).assign(
        Group=lambda d: d["duplicate_group_id"], Row=lambda d: d["input_row"], Name=lambda d: d[NAME].str.strip(),
        State=lambda d: d[STATE], Acres=lambda d: d[AREA], Lat=lambda d: d[LAT], Lon=lambda d: d[LON],
        DamID=lambda d: d["source_id"], Kept=lambda d: (~remove[d.index]).map({True: "yes", False: "no"}),
        Basis=lambda d: [("MANUAL_KEEP" if k else ("representative" if r else "none")) for k, r in
                         zip(d["manual_keep_flag"], d["representative_record_flag"])])
    g1t = g1[["Group", "Row", "Name", "State", "Acres", "Lat", "Lon", "DamID", "Kept", "Basis"]]
    mk = df[keep].sort_values("duplicate_group_id").assign(
        Group=lambda d: d["duplicate_group_id"], Row=lambda d: d["input_row"], DamID=lambda d: d["source_id"],
        Name=lambda d: d[NAME].str.strip(), State=lambda d: d[STATE], Acres=lambda d: d[AREA],
        RepresentativeAlsoKept=lambda d: [int(reps.loc[reps["duplicate_group_id"] == g, "input_row"].iloc[0])
                                          for g in d["duplicate_group_id"]])
    mkt = mk[["Group", "Row", "DamID", "Name", "State", "Acres", "RepresentativeAlsoKept"]]
    gs = (df[is1].groupby("duplicate_group_id").agg(
        Name=(NAME, lambda s: s.iloc[0].strip()), State=(STATE, "first"), Acres=("area_acres", "first"),
        Records=(NAME, "size"), DistinctCoordinates=("group_distinct_coordinates", "first"),
        DistinctDamIDs=("group_distinct_source_ids", "first"), ConflictingFields=("group_attribute_conflicts", "first"))
        .reset_index().rename(columns={"duplicate_group_id": "Group"}))
    gs["km2"] = (gs["Acres"] * ACRE_TO_KM2).round(3)
    same_xy = int((gs["DistinctCoordinates"] == "1").sum())
    high = gs[gs["km2"] >= args.high_area_km2].sort_values("km2", ascending=False)[["Group", "Name", "State", "km2", "Records"]]
    c2 = df[df["name_state_group_id"] != ""]
    c2g = c2.groupby("name_state_group_id").agg(
        Name=(NAME, lambda s: s.iloc[0].strip()), State=(STATE, "first"), Records=(NAME, "size"),
        SmallestAcres=("area_acres", "min"), LargestAcres=("area_acres", "max")).reset_index()
    c2g = c2g[c2g["SmallestAcres"] != c2g["LargestAcres"]].copy()
    c2g["SpreadPct"] = ((c2g["LargestAcres"] - c2g["SmallestAcres"]) / c2g["LargestAcres"] * 100).round(2)
    c2g["LargestKm2"] = (c2g["LargestAcres"] * ACRE_TO_KM2).round(3)
    top2 = c2g.sort_values("LargestAcres", ascending=False).head(15).rename(columns={"name_state_group_id": "Group"})
    close2 = c2g[c2g["SpreadPct"] <= 5].sort_values("SpreadPct").rename(columns={"name_state_group_id": "Group"})
    bins = pd.cut(c2g["SpreadPct"], [-1, 1, 5, 25, 100], labels=["up to 1%", "1 to 5%", "5 to 25%", "over 25%"])
    spread = bins.value_counts().reindex(["up to 1%", "1 to 5%", "5 to 25%", "over 25%"]).rename_axis("Largest-to-smallest area difference").reset_index(name="Groups")
    id_note = df["source_id_status"].value_counts().rename_axis("Identifier status").reset_index(name="Records")
    tol_text = "not set: every same-name, same-state record with a different area is in Category 2" \
        if args.area_tolerance_rel is None else f"{args.area_tolerance_rel:g} (relative)"
    report = f"""# Duplicate review report

Generated {dt.datetime.now().isoformat(timespec='seconds')} by `reservoir_duplicate_review.py` (Python {platform.python_version()}, pandas {pd.__version__}).

**This is a screening result.** A match on name, state and area does not show that two records are the same physical reservoir. `inventory_deduplicated_proposed.csv` is a proposal for review. It replaces nothing.

## 1. Result

| Measure | Value |
|---|---:|
| Original records | {len(df):,} |
| Category 1 groups | {n_groups} |
| Category 1 records | {int(is1.sum())} |
| Category 1 groups kept in full by MANUAL_KEEP | {kept_groups.nunique()} |
| Records kept by MANUAL_KEEP | {int(keep.sum())} ({kept_acres:,.1f} acres) |
| Records proposed for removal | {int(remove.sum())} |
| Category 2 records (manual review) | {int(is2.sum())} |
| Category 3 records (missing information) | {int(is3.sum())} |
| Category 4 records | {int(is4.sum()):,} |
| Records in proposed inventory | {len(proposed):,} |
| Surface area difference | {a0 - a1:,.3f} acres = {km0 - km1:,.3f} km² ({(a0 - a1) / a0:.4%}) |
| FPV-covered area at {args.fpv_coverage:.0%} | {km0 * args.fpv_coverage:,.3f} → {km1 * args.fpv_coverage:,.3f} km² |

## 2. Input data

| Role | Path | Size (bytes) | SHA-256 |
|---|---|---:|---|
| Inventory | `{before['input']['path']}` | {before['input']['size']:,} | `{before['input']['sha256']}` |
| Dam IDs | `{before['id_source']['path']}` | {before['id_source']['size']:,} | `{before['id_source']['sha256']}` |

Columns used: name `{NAME}`, state `{STATE}`, area `{AREA}` (acres, per `merge_natural_lakes_into_nid.py`). No area conversion is used for matching. km² values use {ACRE_TO_KM2} km²/acre for reporting only.

**The inventory has no Dam ID column.** IDs were attached read-only from the NID GeoPackage by an exact match on name, state, latitude and longitude (to 8 decimals) and area, with surrounding spaces removed from IDs. IDs affect only representative selection, never a category.

{table(id_note)}
## 3. Matching method

- **Name:** Unicode NFKC, lowercase, `&` to "and", apostrophes removed, other punctuation replaced by a space, repeated spaces collapsed. Words such as "dam" and "lake" are kept. The original name is preserved.
- **State:** full names and two-letter abbreviations map to the full name. Only matching standardized states are grouped. Unrecognized values go to Category 3.
- **Area:** exact numeric equality on the original value for Category 1. Area tolerance: {tol_text}.
- **Missing values:** a record with a missing name, an unrecognized state, or a missing or non-positive area goes to Category 3 and is never merged.
- **Not used:** fuzzy matching, geographic matching, and Dam ID matching.

## 4. Representative selection

Within each Category 1 group, in order: (1) a valid, uniquely matched Dam ID; (2) the most complete attributes across {', '.join(f'`{c}`' for c in COMPLETENESS if c in df)}; (3) the earliest input row. Areas are not averaged or summed, and no attributes are combined.

## 5. MANUAL_KEEP overrides

The author manually verified the records below on 2026-11-03 as distinct reservoirs that only coincidentally share a name, state and area with another record. They are always retained.

- **Match:** Dam ID, name, state and area together, then validated against the expected input row and group. The run stops if any entry does not match exactly one record.
- **Timing:** applied after detection and representative selection, before the proposed inventory is written.
- **Effect:** both records in each group are retained. Each override record maps to itself. Categories and group IDs are unchanged, so these records remain visible as Category 1 screening matches.
- **Scope:** the rule covers only these records. Detection is unchanged for all other records.

{table(mkt)}
## 6. Category 1 groups

**{n_groups - kept_groups.nunique()} of {n_groups} groups still need review before the proposed inventory is accepted.** Coordinates and Dam IDs below are descriptive and did not affect classification. {n_groups - same_xy} of {n_groups} groups have records with different coordinates, so they may be different water bodies that share a name and area.

{table(gs[['Group', 'Name', 'State', 'Acres', 'km2', 'Records', 'DistinctCoordinates', 'DistinctDamIDs', 'ConflictingFields']])}
{table(g1t)}
## 7. High-area reservoirs affected (at least {args.high_area_km2:g} km²)

{table(high) if len(high) else 'None.'}
## 8. Category 2: manual review

{int(is2.sum())} records in {len(c2g)} name-and-state groups have different areas. All are retained. Many are probably different reservoirs that share a common name.

{table(spread)}
Groups with areas within 5% (closest cases):

{table(close2[['Group', 'Name', 'State', 'Records', 'SmallestAcres', 'LargestAcres', 'SpreadPct']]) if len(close2) else 'None.'}
Largest groups by area:

{table(top2[['Group', 'Name', 'State', 'Records', 'SmallestAcres', 'LargestAcres', 'SpreadPct', 'LargestKm2']])}
Full list: `duplicate_candidates.csv`.

## 9. Missing information

{int(is3.sum())} records are in Category 3.

## 10. Limitations

- **False positives:** common names and rounded areas can match by coincidence.
- **False negatives:** this method cannot see structures of one reservoir that have different names, such as a main dam and its dikes. This is the main limitation.
- **Scale of that limit (descriptive only, no action taken):** {len(shared)} Dam IDs are shared by {int(shared_rows.sum())} records in this input, and only {int((shared_rows & is1).sum())} of those records are in Category 1. Sharing a Dam ID does not by itself show duplication, so these records were not changed.
- **Records with the same key:** where several Dam IDs share an identical name, state, location and area, all candidates are listed and none is chosen.
- **Area data:** matching takes the reported area as given and does not assess whether it is correct.
- **Not recalculated:** electricity, evaporation, AHP rankings and Monte Carlo classifications.

## 11. Validation

{table(pd.DataFrame([(c, 'PASS' if ok else 'FAIL') for c, ok in checks], columns=['Check', 'Result']))}"""
    with open(out / "DUPLICATE_REVIEW_REPORT.md", "x", encoding="utf-8") as f:
        f.write(report)
    print(summary.to_string(index=False))
    if not all_ok:
        sys.exit("VALIDATION FAILED: see DUPLICATE_REVIEW_REPORT.md")


if __name__ == "__main__":
    main()
