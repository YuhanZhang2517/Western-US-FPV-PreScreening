"""02 - Environmental attributes, screening indicators, FPV energy and evaporation for the regional inventory (Pathway A).

Historical sources:
  Roadmap/NID_process.ipynb  cells 13-14 gdf_points_to_da; 16-17 nearest-cell sampling of the ERA5 grids;
                             cell 19 nearest transmission line (sjoin_nearest, EPSG:5070); cell 23 J -> kWh
  merge_natural_lakes_into_nid.py   natural-lake attributes copied from the Top-30 source CSVs (NAT_RENAME)
  input/nid_selected.csv.xlsx       Excel cols O, P, Q (stage 1, author-confirmed M4):
                                    A = acres x 4046.86; E_solar = 0.10 A G; V = 0.10 A PEV
  manuscript Sec. 2.3.1             E_annual = eta E_solar, eta = 0.10 (applied by hand; M3)
  AHP_modified_03_09.ipynb cell 7   State_Score, Ownership_Score functions (applied to raw fields here)
  Rankplot.ipynb / ICE trace        Ice_binary = max ice depth > 0; log_Annual_solar_GWh = log10(0.10 A G)

Regional input (updated 2026-11-04): the approved 8,516-record inventory with the author-approved area corrections
applied, from 01b_deduplication.py. Attributes are
regenerated from the grids and transmission lines as a check, and the run stops if they disagree with the approved
values; calculations then use the approved values. Energy, capacity and CF come from fpv_calculations.py (Eq. 1-4).
The obsolete 0.8-based Capacity_Factor column is never read as a result: CF is recalculated for every record.

Scope: all 8,516 records. Indicators are reported RAW (user decision 2026-10-30): the historical 1-10
decile categorisation was only ever applied to the curated AHP pool and is NOT applied here.
Missing values stay missing (HAB is unavailable for NID records; it is never set to 0).

Evaporation reduction uses the historical implicit 100 % suppression of ERA5 potential evaporation under
the covered area. Every evaporation output is labelled THEORETICAL UPPER BOUND (issue C2/D2, unresolved).

Outputs (outputs/<run-id>/02_data_processing/): see docs/DATA_DICTIONARY.md
Usage: python code/02_data_processing.py [--run-id ID]
"""
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rioxarray  # noqa: F401  (registers the .rio accessor)
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fpv_calculations as K  # noqa: E402
import fpv_config as C  # noqa: E402
import fpv_utils as U   # noqa: E402

NAT_RENAME = {"Annual_solar_potential": "solar_kWhm2", "Annual_evaporation": "evap_m_per_yr",
              "Max_ice_depth": "ice_m", "max_wind_ms": "wind_ms", "nearest_dist_m": "dist_to_grid_m"}
NAT_EXTRA = ["max_HAB_2020_2024", "HAB_flag_20k"]
APPROVED_NUMERIC = ["surfaceArea", "latitude", "longitude", "solar_Jm2", "solar_kWhm2", "evap_m_per_yr", "ice_m",
                    "wind_ms", "dist_to_grid_m", "surfaceArea_sqkm", "max_HAB_2020_2024", "HAB_flag_20k"]
APPROVED_TEXT = ["name", "ownerTypeIds", "primaryOwnerTypeId", "state", "purposeIds", "source_dataset"]
REGENERATION_TOLERANCE = 1e-6          # relative; observed differences are float-storage level (about 1e-7)


# ------------------------------------------------------------------ approved inventory
def load_approved(stage_1b):
    """Corrected rows from 01b, indexed by record_id (input row of the 8,520 CSV). Capacity_Factor is excluded."""
    f = U.require(stage_1b / "inventory_deduplicated_corrected.csv")
    mapping = pd.read_csv(U.require(stage_1b / "duplicate_group_mapping.csv"), dtype=str, keep_default_na=False)
    kept = mapping[~mapping["proposed_action"].str.startswith("remove")]
    text = pd.read_csv(f, dtype=str, keep_default_na=False, na_filter=False)
    num = pd.read_csv(f, float_precision="round_trip", low_memory=False)
    ids = kept["input_row"].astype(int).to_numpy()
    if not (kept["original_name"].to_numpy() == text["name"].to_numpy()).all():
        raise RuntimeError("mapping rows do not align with the approved inventory")
    text.index = num.index = pd.Index(ids, name="record_id")
    return text, num.drop(columns=["Capacity_Factor"]), kept.set_index(pd.Index(ids, name="record_id"))


def regeneration_check(df, num, log):
    """Compare regenerated attributes with the approved values; stop on any real disagreement."""
    a = df.loc[num.index]
    rows = []
    for c in APPROVED_NUMERIC:
        x, y = pd.to_numeric(a[c], errors="coerce"), pd.to_numeric(num[c], errors="coerce")
        both = x.notna() & y.notna()
        rel = ((x - y).abs() / y.abs().clip(lower=1e-9))[both]
        rows.append({"column": c, "records": len(x), "missing_pattern_differs": int((x.isna() != y.isna()).sum()),
                     "max_relative_difference": float(rel.max()) if len(rel) else 0.0})
    for c in APPROVED_TEXT:
        rows.append({"column": c, "records": len(a), "text_values_differ":
                     int((a[c].astype(object).fillna("").astype(str) != num[c].astype(object).fillna("").astype(str)).sum())})
    t = pd.DataFrame(rows).fillna(0)
    bad = t[(t["missing_pattern_differs"] > 0) | (t["max_relative_difference"] > REGENERATION_TOLERANCE) |
            (t["text_values_differ"] > 0)]
    if len(bad):
        raise RuntimeError(f"regenerated attributes differ from the approved inventory:\n{bad.to_string()}")
    log.info(f"regeneration check passed: largest relative difference {t.max_relative_difference.max():.2e}")
    return t


# ------------------------------------------------------------------ NID_process cells 13-17
def gdf_points_to_da(gdf, value_col, x_col="longitude", y_col="latitude", crs="EPSG:4326"):
    df = gdf[[x_col, y_col, value_col]].dropna().copy()
    df = df.groupby([y_col, x_col], as_index=False)[value_col].mean()
    piv = df.pivot(index=y_col, columns=x_col, values=value_col)
    lats = np.sort(piv.index.values)[::-1]
    lons = piv.columns.values
    data = piv.reindex(index=lats[::-1]).to_numpy()[::-1]
    da = xr.DataArray(data, coords={"latitude": lats, "longitude": lons}, dims=("latitude", "longitude"),
                      name=value_col)
    da = da.rio.set_spatial_dims(x_dim="longitude", y_dim="latitude", inplace=False)
    return da.rio.write_crs(crs)


def sample_grids(pts, log):
    vals = {}
    for col, (path, layer, vcol) in C.ERA5_GRIDS.items():
        g = gpd.read_file(U.require(path), layer=layer)
        da = gdf_points_to_da(g, vcol)
        p = pts.to_crs(da.rio.crs)
        vals[col] = da.sel(longitude=xr.DataArray(p.geometry.x.values, dims="z"),
                           latitude=xr.DataArray(p.geometry.y.values, dims="z"), method="nearest").values
        log.info(f"sampled {col} from {path.name} (nearest grid cell)")
    return pd.DataFrame(vals, index=pts.index)


def transmission_distance(pts, log):
    """Cell 19: clip lines to the western mask; nearest line in EPSG:5070; keep the closest per point."""
    states = gpd.read_file(U.require(C.STATE_SHP))
    mask = states[states["NAME"].isin(C.WESTERN_STATES)].to_crs(4326).dissolve().buffer(0)
    lines = gpd.clip(gpd.read_file(U.require(C.TRANSMISSION_SHP)).to_crs(4326), mask)
    a = pts[["geometry"]].to_crs(C.PROJECTED_CRS).assign(_left_id=pts.index.values).reset_index(drop=True)
    b = lines[["geometry"]].to_crs(C.PROJECTED_CRS).reset_index(drop=True)
    near = gpd.sjoin_nearest(a, b, how="left", distance_col="dist_to_grid_m")
    near = near.sort_values("dist_to_grid_m").drop_duplicates(subset="_left_id", keep="first")
    log.info(f"nearest transmission line computed for {len(near):,} points ({len(lines):,} line features)")
    return near.set_index("_left_id")["dist_to_grid_m"].reindex(pts.index)


# ------------------------------------------------------------------ AHP notebook cell 7 functions
def ownership_score(value):
    if pd.isna(value):
        return np.nan                    # missing stays missing here (cell 7 returned 0 inside the AHP pool)
    v = str(value).lower()
    s = 0
    s += 5 if "federal" in v else 0
    s += 4 if "state" in v else 0
    s += 3 if any(w in v for w in ["local", "tribe", "tribal", "county", "city", "municipal"]) else 0
    s += 2 if ("public utility" in v or "utility" in v) else 0
    s += 1 if "private" in v else 0
    return s


def state_score(state):
    if pd.isna(state):
        return np.nan
    return C.STATE_SCORES.get(str(state).upper().strip(), C.STATE_SCORE_DEFAULT)


def totals(df, acre_to_m2):
    a = pd.to_numeric(df["surfaceArea"], errors="coerce").fillna(0.0) * acre_to_m2
    m = K.fpv_metrics(a / 1e6, df["solar_kWhm2"])
    return {"records": len(df), "water_area_km2": a.sum() / 1e6, "fpv_area_km2": m["fpv_area_km2"].sum(),
            "installed_capacity_GW": m["installed_capacity_MW"].sum() / 1e3,
            "incident_solar_TWh_per_yr": m["incident_solar_kWh_per_yr"].sum() / 1e9,
            "electricity_TWh_per_yr": m["annual_electricity_MWh"].sum() / 1e6,
            "capacity_factor_capacity_weighted": K.capacity_weighted_cf(m["annual_electricity_MWh"], m["installed_capacity_MW"]),
            "evap_reduction_upper_bound_km3_per_yr":
                (C.F_COV * a * df["evap_m_per_yr"] * C.EVAP_SUPPRESSION_FRACTION).sum() / 1e9}


def group_totals(ind):
    """State and regional aggregates of the site-level values."""
    def agg(d):
        cf = d["Capacity_Factor"]
        return {"records": len(d), "water_area_km2": d["surface_area_km2"].sum(), "fpv_area_km2": d["fpv_area_km2"].sum(),
                "installed_capacity_GW": d["installed_capacity_MW"].sum() / 1e3,
                "electricity_TWh_per_yr": d["electricity_kWh_per_yr"].sum() / 1e9,
                "evap_reduction_upper_bound_km3_per_yr": d["evap_reduction_upper_bound_m3_per_yr"].sum() / 1e9,
                "cf_capacity_weighted": K.capacity_weighted_cf(d["electricity_kWh_per_yr"] / 1e3, d["installed_capacity_MW"]),
                "cf_median": cf.median(), "cf_min": cf.min(), "cf_max": cf.max()}
    rows = [{"state": s, **agg(d)} for s, d in ind.groupby("state", sort=True)]
    return pd.DataFrame(rows + [{"state": "ALL", **agg(ind)}])


def main():
    args = U.parse_args(__doc__.splitlines()[0])
    U.install_write_guard()
    src = U.stage_dir(args.run_id, "1b", create=False)
    out = U.stage_dir(args.run_id, 2)
    log = U.get_logger(out, "02_data_processing")
    inv_path = U.require(src / "inventory_8516.gpkg")
    inv = gpd.read_file(inv_path).set_index("record_id", drop=False)
    if len(inv) != C.EXPECTED_REGIONAL_RECORDS:
        raise RuntimeError(f"expected {C.EXPECTED_REGIONAL_RECORDS} records, found {len(inv)}")
    log.info(f"inventory: {len(inv):,} records (approved deduplicated inventory)")
    approved_text, approved_num, kept = load_approved(src)

    # ---- 1. environmental attributes ---------------------------------------------------------
    is_nat = inv["is_natural_water_body"].astype(bool)
    nid = inv[~is_nat]
    env = sample_grids(nid, log)
    if C.TRANSMISSION_SHP.exists():
        env["dist_to_grid_m"] = transmission_distance(nid, log)
    else:
        log.warning("transmission lines not supplied: dist_to_grid_m not regenerated; approved values are used")
        env["dist_to_grid_m"] = approved_num["dist_to_grid_m"].reindex(env.index)
    env["solar_kWhm2"] = env["solar_Jm2"].astype(float) / C.J_PER_KWH
    env["env_provenance"] = "sampled: processed ERA5 grids (nearest cell) + HIFLD lines (EPSG:5070)"

    nat_rows = []
    for rid, r in inv[is_nat].iterrows():
        f = C.NATURAL_LAKE_SOURCE_DIR / r["natural_lake_source_file"]
        s = pd.read_csv(U.require(f))
        s = s[s["Name"] == r["name"]].iloc[0]
        rec = {"record_id": rid, "solar_Jm2": np.nan}
        rec.update({new: pd.to_numeric(s[old], errors="coerce") for old, new in NAT_RENAME.items()})
        rec.update({c: pd.to_numeric(s.get(c, np.nan), errors="coerce") for c in NAT_EXTRA})
        rec["env_provenance"] = f"copied from {f.name} (NHD branch; upstream polygons and code unavailable)"
        nat_rows.append(rec)
    nat_env = pd.DataFrame(nat_rows).set_index("record_id")
    env = pd.concat([env, nat_env])
    df = pd.DataFrame(inv.drop(columns="geometry")).join(env)
    for c in NAT_EXTRA:
        if c not in df:
            df[c] = np.nan

    # regenerated attributes must agree with the approved inventory; calculations then use approved values
    regeneration_check(df, approved_num, log).to_csv(out / "regeneration_check.csv", index=False)
    for c in APPROVED_NUMERIC + APPROVED_TEXT:
        df[c] = approved_num[c].reindex(df.index)

    # ---- 2. raw screening indicators (no categorisation) ----------------------------------------
    a_m2 = df["surfaceArea"].astype(float) * C.ACRE_TO_M2_EXCEL
    ind = df[["record_id", "nidId", "federalId", "name", "state", "latitude", "longitude", "source_dataset",
              "is_natural_water_body"]].reset_index(drop=True)
    df = df.reset_index(drop=True)
    a_m2 = a_m2.reset_index(drop=True)
    ind["surface_area_km2"] = a_m2 / 1e6
    fpv = K.fpv_metrics(a_m2 / 1e6, df["solar_kWhm2"])          # Eq. 1-4 for every record
    K.assert_cf_follows_eq3(fpv["Capacity_Factor"], df["solar_kWhm2"])   # no result is written unless this holds
    ind["fpv_area_km2"] = fpv["fpv_area_km2"]
    ind["installed_capacity_MW"] = fpv["installed_capacity_MW"]
    ind["Annual_evaporation"] = df["evap_m_per_yr"]
    ind["Ice_binary"] = np.where(df["ice_m"].isna(), np.nan, (df["ice_m"] > C.ICE_THRESHOLD_M).astype(float))
    ind["max_wind_ms"] = df["wind_ms"]
    ind["nearest_dist_m"] = df["dist_to_grid_m"]
    ind["Annual_solar_GWh_10pct"] = C.F_COV * df["surfaceArea_sqkm"] * df["solar_kWhm2"]
    ind["log_Annual_solar_GWh"] = np.log10(ind["Annual_solar_GWh_10pct"])
    ind["Capacity_Factor"] = fpv["Capacity_Factor"]
    ind["HAB_flag_20k"] = df["HAB_flag_20k"]
    ind["Ownership_Score"] = df["ownerTypeIds"].apply(ownership_score)
    ind["State_Score"] = df["state"].apply(state_score)
    ind["ownership_text"] = df["ownerTypeIds"]
    ind["env_provenance"] = df["env_provenance"]
    ind["HAB_status"] = np.where(df["HAB_flag_20k"].notna(), "observed (copied from curated CSV)",
                                 "MISSING: CyAN inputs and code unavailable (not zero)")
    # energy and water (per record)
    ind["incident_solar_kWh_per_yr"] = fpv["incident_solar_kWh_per_yr"]
    ind["electricity_kWh_per_yr"] = fpv["annual_electricity_MWh"] * K.KWH_PER_MWH
    ind["evap_reduction_upper_bound_m3_per_yr"] = C.F_COV * a_m2 * df["evap_m_per_yr"] * C.EVAP_SUPPRESSION_FRACTION
    ind.to_csv(out / "regional_indicators_8516.csv", index=False)

    # ---- publication dataset: approved values verbatim + calculated columns -----------------------
    pub = approved_text.drop(columns=["Capacity_Factor"]).copy()
    pos = list(approved_text.columns).index("Capacity_Factor")
    pub.insert(pos, "Capacity_Factor", ind["Capacity_Factor"].to_numpy())
    pub.insert(0, "source_id_status", kept["source_id_status"])
    pub.insert(0, "source_id", kept["source_id"])
    pub.insert(0, "record_id", pub.index)
    pub["surface_area_km2"] = ind["surface_area_km2"].to_numpy()
    for c in ["fpv_area_km2", "installed_capacity_MW", "incident_solar_kWh_per_yr"]:
        pub[c] = ind[c].to_numpy()
    pub["annual_electricity_MWh"] = fpv["annual_electricity_MWh"].to_numpy()
    pub["evap_reduction_upper_bound_m3_per_yr"] = ind["evap_reduction_upper_bound_m3_per_yr"].to_numpy()
    pub["cf_status"] = fpv["cf_status"].to_numpy()
    pub["cf_missing_reason"] = fpv["cf_missing_reason"].to_numpy()
    flags = pd.read_csv(U.require(C.AREA_REVIEW_FLAGS), dtype=str)
    flag_keys = set(zip(flags["nidId"], flags["name"].str.strip()))
    pub["area_review_flag"] = [(i, n.strip()) in flag_keys for i, n in zip(pub["source_id"], pub["name"])]
    if int(pub["area_review_flag"].sum()) != len(flags):
        raise RuntimeError("area review flags did not all match the inventory")
    # the flags describe source values, so a corrected record leaves the flagged set; its source area stays visible
    corrected = pd.read_csv(U.require(src / "surface_area_corrections_applied.csv")).set_index("record_id")
    pub["surfaceArea_source_acres"] = pd.to_numeric(pub["surfaceArea"])
    pub.loc[corrected.index, "surfaceArea_source_acres"] = corrected["original_surfaceArea_acres"]
    pub["area_correction_applied"] = pub.index.isin(corrected.index)
    pub.loc[corrected.index, "area_review_flag"] = False
    log.info(f"{len(corrected)} area correction(s) applied; {int(pub['area_review_flag'].sum())} area review flags remain")
    pub.to_csv(out / "regional_fpv_inventory_8516.csv", index=False)
    group_totals(ind).to_csv(out / "regional_state_totals.csv", index=False)

    # ---- 3. missing-value documentation ----------------------------------------------------------
    rows = []
    for c in ["Annual_evaporation", "Ice_binary", "max_wind_ms", "nearest_dist_m", "log_Annual_solar_GWh",
              "Capacity_Factor", "HAB_flag_20k", "Ownership_Score", "State_Score"]:
        for grp, sub in [("NID", ind[~ind.is_natural_water_body]), ("NHD", ind[ind.is_natural_water_body])]:
            v = sub[c]
            rows.append({"indicator": c, "source_dataset": grp, "records": len(v), "observed": int(v.notna().sum()),
                         "missing": int(v.isna().sum()), "observed_zero": int((v == 0).sum()),
                         "observed_negative": int((v < 0).sum())})
    pd.DataFrame(rows).to_csv(out / "indicator_missingness.csv", index=False)

    # ---- 4. regional totals ----------------------------------------------------------------------
    gsl = df["name"].str.strip().str.lower() == "great salt lake"
    pops = [(f"all records ({len(df):,} inventory)", df), (f"NID records ({int((~is_nat).sum()):,})", df[~is_nat.values]),
            ("natural lakes (13)", df[is_nat.values]), ("Great Salt Lake", df[gsl.values])]
    trows = []
    for label, sub in pops:
        for fac_label, fac in [("4046.86 (Excel, primary)", C.ACRE_TO_M2_EXCEL),
                               ("4046.856 (merge script, sensitivity)", C.ACRE_TO_M2_MERGE)]:
            trows.append({"population": label, "acre_to_m2": fac_label, **totals(sub, fac)})
    tot = pd.DataFrame(trows)
    tot["evaporation_assumption"] = "100% suppression of ERA5 potential evaporation under FPV (THEORETICAL UPPER BOUND)"
    tot.to_csv(out / "regional_totals.csv", index=False)
    t = tot.iloc[0]
    log.info(f"{len(df):,} records: installed capacity {t.installed_capacity_GW:.2f} GW; electricity "
             f"{t.electricity_TWh_per_yr:.2f} TWh/yr; evaporation reduction "
             f"{t.evap_reduction_upper_bound_km3_per_yr:.4f} km3/yr (theoretical upper bound)")

    # ---- 5. repeated nidId impact sizing (no correction) -----------------------------------------
    rep = ind[ind["nidId"].notna() & ind["nidId"].duplicated(keep=False)].sort_values(["nidId", "record_id"])
    if len(rep):
        same = rep.groupby("nidId")["surface_area_km2"].transform("nunique") == 1
        imp = []
        for lab, sub in [("groups with identical area on every record", rep[same]), ("all repeated-nidId groups", rep)]:
            extra = sub.groupby("nidId")[["surface_area_km2", "electricity_kWh_per_yr",
                                          "evap_reduction_upper_bound_m3_per_yr"]].apply(lambda d: d.sum() - d.iloc[0]).sum()
            imp.append({"subset": lab, "nidIds": sub["nidId"].nunique(), "records": len(sub),
                        "area_on_2nd_and_later_records_km2": extra["surface_area_km2"],
                        "electricity_on_2nd_and_later_records_TWh": extra["electricity_kWh_per_yr"] / 1e9,
                        "evap_upper_bound_on_2nd_and_later_records_km3": extra["evap_reduction_upper_bound_m3_per_yr"] / 1e9,
                        "note": "impact sizing only; records are NOT removed (decision D1 unresolved)"})
        pd.DataFrame(imp).to_csv(out / "repeated_nidId_impact.csv", index=False)

    U.write_manifest(out, "02_data_processing.py",
                     [inv_path, src / "inventory_deduplicated_proposed.csv", C.AREA_REVIEW_FLAGS] +
                     ([C.STATE_SHP, C.TRANSMISSION_SHP] if C.TRANSMISSION_SHP.exists() else []) +
                     [p for p, _, _ in C.ERA5_GRIDS.values()] +
                     [C.NATURAL_LAKE_SOURCE_DIR / f for f in C.TOP30_FILE_ORDER_FOR_LAKES],
                     {"f_cov": C.F_COV, "eta": C.ETA, "power_density_MW_per_km2": C.POWER_DENSITY_MW_PER_KM2,
                      "performance_ratio": "none", "acre_to_m2": C.ACRE_TO_M2_EXCEL,
                      "evap_suppression_fraction": C.EVAP_SUPPRESSION_FRACTION, "J_per_kWh": C.J_PER_KWH,
                      "hours_per_year": C.HOURS_PER_YEAR, "ice_threshold_m": C.ICE_THRESHOLD_M,
                      "projected_crs": C.PROJECTED_CRS, "regional_standardisation": "none (raw indicators only)"},
                     ["Evaporation reduction = theoretical upper bound (100 % PEV suppression, implicit in the "
                      "historical Excel formula; decision D2 unresolved).",
                      "Capacity_Factor = Eq. 3 for every record (equals G/8760); no performance ratio.",
                      "Installed capacity is in MW as in the manuscript; DC or AC is not stated there.",
                      "HAB missing for all NID records (not zero). Ownership_Score/State_Score are the AHP "
                      "functions applied to raw NID text; the curated pool's ownership text has another lineage."])
    log.info("done")


if __name__ == "__main__":
    main()
