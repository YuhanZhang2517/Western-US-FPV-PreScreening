"""01b - Duplicate review, manual keep overrides and the 8,516-record regional inventory (Pathway A).

Order: 01 builds the 8,520-record inventory -> this script runs reservoir_duplicate_review.py on the 8,520-record CSV
-> checks the result against the approved files, stopping on any difference -> carries the retained records into
the pipeline by exact key, because 01's row order differs from the CSV's row order -> applies the author-approved
surface-area corrections in data/regional/corrections/, so the source value stays visible and every change is listed.

record_id in all later stages is the input row of the 8,520-record CSV, so it matches duplicate_group_mapping.csv.
Dam IDs for the two rows whose exact key has two candidate IDs are left blank here; see source_id in the mapping.

Outputs (outputs/<run-id>/01b_deduplication/): the five duplicate-review outputs (before correction),
  inventory_deduplicated_corrected.csv, surface_area_corrections_applied.csv,
  inventory_8516.gpkg/.csv (corrected), records_removed.csv, figure1_statistics_8516.csv, verification.csv,
  run_manifest.json
Usage: python code/01b_deduplication.py [--run-id ID]
"""
import importlib.util
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fpv_config as C  # noqa: E402
import fpv_utils as U   # noqa: E402

COMPARED = ["inventory_deduplicated_proposed.csv", "duplicate_group_mapping.csv", "duplicate_candidates.csv",
            "duplicate_summary.csv"]


def load_module(filename, name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def keyed(d):
    """Exact record key with an occurrence number, so identical rows stay one-to-one."""
    k = pd.DataFrame({"name": d["name"].astype(str), "state": d["state"].astype(str),
                      "lat": pd.to_numeric(d["latitude"]).round(6), "lon": pd.to_numeric(d["longitude"]).round(6),
                      "area": pd.to_numeric(d["surfaceArea"]).round(4)}, index=d.index)
    k["n"] = k.groupby(["name", "state", "lat", "lon", "area"]).cumcount()
    return k


def apply_area_corrections(out_inv, approved_csv, kept, out, log):
    """Apply the corrections table to the pipeline inventory and to the approved CSV. Stop unless each one matches
    exactly one record at its documented source value. Only surfaceArea and surfaceArea_sqkm change."""
    corr = pd.read_csv(U.require(C.AREA_CORRECTIONS), dtype={"source_id": str})
    text = pd.read_csv(approved_csv, dtype=str, keep_default_na=False, na_filter=False)
    ids = kept["input_row"].astype(int).to_numpy()
    if not (kept["original_name"].to_numpy() == text["name"].to_numpy()).all():
        raise RuntimeError("mapping rows do not align with the approved inventory")
    original, applied = text.copy(), []
    for c in corr.itertuples(index=False):
        rows = np.where((kept["source_id"].to_numpy() == c.source_id) & (text["name"].to_numpy() == c.name) &
                        (text["state"].to_numpy() == c.state))[0]
        if len(rows) != 1:
            raise RuntimeError(f"correction for {c.name} matched {len(rows)} records")
        i, rid = rows[0], int(ids[rows[0]])
        p = np.where(out_inv["record_id"].to_numpy() == rid)[0]
        if len(p) != 1 or float(text.at[i, "surfaceArea"]) != c.original_surfaceArea_acres \
                or float(out_inv.iloc[p[0]]["surfaceArea"]) != c.original_surfaceArea_acres:
            raise RuntimeError(f"{c.name}: source area is not the documented {c.original_surfaceArea_acres} acres")
        sqkm = c.corrected_surfaceArea_acres * C.ACRE_TO_SQKM
        text.at[i, "surfaceArea"], text.at[i, "surfaceArea_sqkm"] = repr(float(c.corrected_surfaceArea_acres)), repr(sqkm)
        out_inv.loc[out_inv.index[p[0]], ["surfaceArea", "surfaceArea_sqkm"]] = [c.corrected_surfaceArea_acres, sqkm]
        applied.append({"record_id": rid, **c._asdict(), "corrected_surfaceArea_sqkm": sqkm})
        log.info(f"area correction: {c.name} ({c.source_id}) {c.original_surfaceArea_acres:,} -> "
                 f"{c.corrected_surfaceArea_acres:,} acres")
    changed = int((text != original).sum().sum())
    if changed != 2 * len(corr) or set((text != original).any()[lambda s: s].index) != {"surfaceArea", "surfaceArea_sqkm"}:
        raise RuntimeError(f"area correction changed unexpected cells: {changed}")
    text.to_csv(out / "inventory_deduplicated_corrected.csv", index=False)
    pd.DataFrame(applied).to_csv(out / "surface_area_corrections_applied.csv", index=False)
    return [{"check": "area corrections match one record each at the documented source value", "passed": True},
            {"check": "area corrections change only surfaceArea and surfaceArea_sqkm of the listed records",
             "passed": True}]


def main():
    args = U.parse_args(__doc__.splitlines()[0])
    U.install_write_guard()
    s1 = U.stage_dir(args.run_id, 1, create=False)
    out = U.stage_dir(args.run_id, "1b")
    log = U.get_logger(out, "01b_deduplication")

    # ---- 1. duplicate review, in-process so the write guard stays active
    review = load_module("reservoir_duplicate_review.py", "reservoir_duplicate_review")
    sys.argv = ["reservoir_duplicate_review.py", "--input", str(U.require(C.INVENTORY_8520_CSV)),
                "--id-source", str(U.require(C.NID_GPKG)), "--output-dir", str(out)]
    review.main()

    # ---- 2. must equal the approved files
    checks = []
    for f in COMPARED:
        same = U.sha256(out / f) == U.sha256(U.require(C.APPROVED_DIR / f))
        checks.append({"check": f"{f} byte-identical to approved file", "passed": same})
    mapping = pd.read_csv(out / "duplicate_group_mapping.csv", dtype=str, keep_default_na=False)
    keep_rows = set(mapping.loc[mapping["manual_keep_flag"] == "True", "input_row"].astype(int))
    expected_keep = {k["input_row"] for k in review.MANUAL_KEEP}
    checks.append({"check": "MANUAL_KEEP records are the listed records", "passed": keep_rows == expected_keep})
    kept = mapping[~mapping["proposed_action"].str.startswith("remove")]
    checks.append({"check": "retained count equals approved count", "passed": len(kept) == C.EXPECTED_REGIONAL_RECORDS})
    pd.DataFrame(checks).to_csv(out / "verification.csv", index=False)
    if not all(c["passed"] for c in checks):
        raise RuntimeError(f"duplicate review differs from the approved dataset: {checks}")
    log.info(f"duplicate review reproduces the approved dataset: {len(kept):,} records; "
             f"{len(keep_rows)} MANUAL_KEEP overrides applied")

    # ---- 3. carry retained records into the pipeline by exact key
    inv = gpd.read_file(U.require(s1 / "inventory_8520.gpkg")).rename(columns={"record_id": "script01_record_id"})
    csv8520 = pd.read_csv(C.INVENTORY_8520_CSV, float_precision="round_trip", low_memory=False)
    csv8520.insert(0, "record_id", np.arange(1, len(csv8520) + 1))
    joined = keyed(inv).assign(pos=np.arange(len(inv))).merge(
        keyed(csv8520).assign(record_id=csv8520["record_id"]), on=["name", "state", "lat", "lon", "area", "n"], how="outer",
        indicator=True)
    if not (joined["_merge"] == "both").all() or len(joined) != len(inv):
        raise RuntimeError("01 inventory does not match the 8,520-record CSV one to one")
    inv["record_id"] = joined.set_index("pos")["record_id"].astype(int).reindex(np.arange(len(inv))).to_numpy()
    retained = set(kept["input_row"].astype(int))
    out_inv = inv[inv["record_id"].isin(retained)].sort_values("record_id").reset_index(drop=True)
    ambiguous = set(kept.loc[kept["source_id_status"].str.startswith("ambiguous"), "input_row"].astype(int))
    # Dam IDs come from the mapping, so both entry points give the same IDs; ambiguous keys stay blank
    ids = kept.set_index(kept["input_row"].astype(int))["source_id"]
    out_inv["nidId"] = out_inv["record_id"].map(ids).replace("", None).astype(object)
    out_inv.loc[out_inv["record_id"].isin(ambiguous), ["nidId", "federalId"]] = None
    checks += apply_area_corrections(out_inv, out / "inventory_deduplicated_proposed.csv", kept, out, log)
    pd.DataFrame(checks).to_csv(out / "verification.csv", index=False)
    out_inv.to_file(out / "inventory_8516.gpkg", driver="GPKG")
    pd.DataFrame(out_inv.drop(columns="geometry")).to_csv(out / "inventory_8516.csv", index=False)
    mapping[mapping["proposed_action"].str.startswith("remove")].to_csv(out / "records_removed.csv", index=False)

    # ---- 4. Figure 1 statistics on the new inventory
    prep = load_module("01_data_preparation.py", "prep")
    nid_only = out_inv[~out_inv["is_natural_water_body"].astype(bool)]
    pd.DataFrame([prep.figure1_statistics(out_inv, f"{len(out_inv):,} inventory (NID + 13 natural lakes)"),
                  prep.figure1_statistics(nid_only, f"{len(nid_only):,} NID records only")]) \
        .to_csv(out / "figure1_statistics_8516.csv", index=False)

    U.write_manifest(out, "01b_deduplication.py",
                     [C.INVENTORY_8520_CSV, C.NID_GPKG, C.AREA_CORRECTIONS] + [C.APPROVED_DIR / f for f in COMPARED],
                     {"manual_keep": review.MANUAL_KEEP, "area_tolerance": None, "records_in": len(inv),
                      "records_out": len(out_inv)},
                     ["Screening result: name, state and area matching does not prove physical identity.",
                      "Dikes and saddle dams with different names are not removed by this rule."])
    log.info("done")


if __name__ == "__main__":
    main()
