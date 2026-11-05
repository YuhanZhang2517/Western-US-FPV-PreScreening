"""Check a workflow run: recompute every regional record from the formulas and compare outputs with results/reference/.
Independent of the workflow modules. Usage: python code/validate_results.py [--run-id run]
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("--run-id", default="run")
args = ap.parse_args()
RUN, REF = ROOT / "outputs" / args.run_id, ROOT / "results" / "reference"
FAILS = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


rd = lambda p: pd.read_csv(p, float_precision="round_trip", low_memory=False)
d = rd(RUN / "02_data_processing/regional_fpv_inventory_8516.csv")
ok(len(d) == 8516 and d["record_id"].is_unique, "8,516 unique regional records")
A = d["surfaceArea"] * 4046.86 / 1e6                     # km2
Afpv = 0.10 * A                                          # Eq. 1
Esolar = d["solar_kWhm2"] * Afpv * 1e6                   # Eq. 2, kWh/yr
E = 0.10 * Esolar / 1e3                                  # Eq. 4, MWh/yr
P = 100.0 * Afpv                                         # MW
CF = E / (P * 8760.0)                                    # Eq. 3
for name, new, col in [("FPV area", Afpv, "fpv_area_km2"), ("installed capacity", P, "installed_capacity_MW"),
                       ("electricity", E, "annual_electricity_MWh"), ("capacity factor", CF, "Capacity_Factor")]:
    ok(float((new / d[col] - 1).abs().max()) < 1e-12, f"site-level {name} recomputed for all records")
ok(float((d["Capacity_Factor"] / (d["solar_kWhm2"] / 8760) - 1).abs().max()) < 1e-12, "Capacity_Factor = G/8760")
ok(bool(np.isfinite(d[["Capacity_Factor", "installed_capacity_MW", "annual_electricity_MWh"]].to_numpy()).all()), "all values finite")
ok(bool((d["cf_status"] == "calculated").all()), "all 8,516 records have a calculated CF")
ref = rd(ROOT / "data/regional/regional_fpv_inventory_8516.csv")
ok(ref.shape == d.shape, "regional dataset has the reference shape")
num = ref.select_dtypes("number").columns
ok(float(((d[num] - ref[num]).abs() / ref[num].abs().clip(lower=1e-9)).max().max()) < 1e-9, "regional dataset equals the reference")
# Area corrections: rebuild the corrected inputs from the approved inventory and the corrections table only
appr = rd(ROOT / "data/regional/review/inventory_deduplicated_proposed.csv")
corr = rd(ROOT / "data/regional/corrections/surface_area_corrections.csv")
ok(len(appr) == len(d) and (appr["name"].to_numpy() == d["name"].to_numpy()).all(), "dataset rows align with the approved inventory")
hit = d["source_id"].isin(corr["source_id"]) & d["name"].isin(corr["name"])
ok(int(hit.sum()) == len(corr) == int(d["area_correction_applied"].sum()), "each area correction is applied to exactly one record")
acres = appr["surfaceArea"].copy()
for c in corr.itertuples():
    ok(float(appr.loc[(d["source_id"] == c.source_id) & (d["name"] == c.name), "surfaceArea"].iloc[0]) == c.original_surfaceArea_acres, f"{c.name}: approved inventory holds the documented source area")
    row = d[(d["source_id"] == c.source_id) & (d["name"] == c.name)].iloc[0]
    ok(row["surfaceArea"] == c.corrected_surfaceArea_acres and row["surfaceArea_source_acres"] == c.original_surfaceArea_acres, f"{c.name}: corrected area used, source area retained")
    ok(abs(row["surfaceArea_sqkm"] / (c.corrected_surfaceArea_acres * 0.00404685642) - 1) < 1e-12 and abs(row["surface_area_km2"] / (c.corrected_surfaceArea_acres * 4046.86e-6) - 1) < 1e-12, f"{c.name}: both area columns follow the corrected acres")
    acres[(d["source_id"] == c.source_id) & (d["name"] == c.name)] = c.corrected_surfaceArea_acres
same = [c for c in appr.columns if c not in ("Capacity_Factor", "surfaceArea", "surfaceArea_sqkm")]
ok(all(appr[c].equals(d[c]) or np.allclose(appr[c], d[c], rtol=0, atol=0, equal_nan=True) for c in same), "all other input attributes equal the approved inventory")
ok(bool((d.loc[~hit, "surfaceArea"] == appr.loc[~hit, "surfaceArea"]).all()), "no other surface area changed")
ok(int(d["area_review_flag"].sum()) == len(rd(ROOT / "data/regional/review/area_review_flags_19.csv")) - len(corr), "area review flags exclude corrected records")
A2 = acres * 4046.86                                     # m2, from the input files alone
t0 = rd(RUN / "02_data_processing/regional_totals.csv").iloc[0]
for name, new, col in [("water area", A2.sum() / 1e6, "water_area_km2"), ("FPV area", 0.10 * A2.sum() / 1e6, "fpv_area_km2"),
                       ("installed capacity", 100.0 * 0.10 * A2.sum() / 1e6 / 1e3, "installed_capacity_GW"),
                       ("electricity", (0.10 * 0.10 * A2 * appr["solar_kWhm2"]).sum() / 1e9, "electricity_TWh_per_yr"),
                       ("evaporation", (0.10 * A2 * appr["evap_m_per_yr"]).sum() / 1e9, "evap_reduction_upper_bound_km3_per_yr")]:
    ok(abs(new / t0[col] - 1) < 1e-12, f"regional {name} recomputed from the input files: {new:.4f}")
t, tr = rd(RUN / "02_data_processing/regional_totals.csv"), rd(REF / "regional_totals.csv")
nums = t.select_dtypes("number").columns
ok(float(((t[nums] - tr[nums]).abs() / tr[nums].abs().clip(lower=1e-9)).max().max()) < 1e-9, "regional totals equal the reference")
s = rd(RUN / "02_data_processing/regional_state_totals.csv").set_index("state")
for c in ["records", "installed_capacity_GW", "electricity_TWh_per_yr", "evap_reduction_upper_bound_km3_per_yr"]:
    ok(abs(s.drop("ALL")[c].sum() / s.loc["ALL", c] - 1) < 1e-12, f"state sums equal regional total: {c}")
r, rr = rd(RUN / "03_AHP_analysis/integrated_dam_rankings_ahp.csv"), rd(ROOT / "data/ahp/ahp_candidates_138.csv")
ok(len(r) == 138, "138 AHP candidates")
cats = [c for c in r if c.endswith("_category")]
ok((r["Name"] == rr["Name"]).all() and (r["Rank"] == rr["Rank"]).all() and r[cats].equals(rr[cats]), "AHP ranks and categories equal the reference")
ok(float((r["Capacity_Factor"] / (r["Annual_solar_potential"] / 8760) - 1).abs().max()) < 1e-12, "AHP Capacity_Factor = G/8760")
for f in ["sensitivity_robustness_metrics.csv", "robustness_class_summary.csv", "table3_HR_vs_WS.csv", "table2_mannwhitney_main.csv"]:
    a, b = rd(RUN / "04_sensitivity_analysis" / f), rd(REF / f)
    n = a.select_dtypes("number").columns
    ok(a.shape == b.shape and (len(n) == 0 or float((a[n] - b[n]).abs().max().max()) < 1e-9), f"{f} equals the reference")
figs = ["figure1_surface_area_distribution", "figure3_top5_contributions", "figure4_top30_state_ownership", "figure5_rank_uncertainty"]
ok(all((RUN / "05_figures" / f"{f}.png").stat().st_size > 0 for f in figs), "figures 1, 3, 4 and 5 were drawn")
print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
