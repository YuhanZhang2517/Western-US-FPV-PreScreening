"""03 - AHP analysis on the manually curated candidate pool (Pathway B).

Historical source: Roadmap/AHP_modified_03_09.ipynb (producer of output version A, 2026-09-28)
  cell 2  variables, directions, binary flags          cell 3  load the 5 curated CSVs
  cell 6  (Name, State) de-duplication + ownership merge cell 7  State_Score / Ownership_Score
  cell 9  eigenvector weights and CR                     cell 12 1-10 decile categorisation
  cell 13 AHP score   cell 14 rank   cell 16 save        cell 31 Spearman / VIF diagnostics
plus scripts/reconstructed/r1_ahp_aggregation.py (geometric mean of the 100 simulated matrices; the
aggregation code itself is not on disk) and the expert scenarios of
Roadmap/output/expert_scale_analysis/notebooks/AHP_modified_03_09_two_experts.ipynb (cells 14-15).

Inputs (working copies; never modified):
  pathway_B/curated_top30/*_Top30_Solar_cleaned.csv     AUTHORITATIVE manually curated inputs (149 rows)
  pathway_B/ahp_matrices/AHP_Saaty_random_experts_alpha10_byStakeholder.xlsx   100 simulated matrices
  pathway_B/ahp_matrices/CF438420.xlsx                   historical aggregate (verification + optional route)
  pathway_B/expert_matrices/{Rob,TomLang (2)}.xlsx       real-expert judgments (comparison scenarios)

Weights: by default the group matrix is RE-COMPUTED as the element-wise geometric mean of ALL 100
simulated matrices (no CR-based exclusion; author-confirmed M1). `--weights-source saved_aggregate`
reads CF438420.xlsx instead, exactly as the notebook did; both routes are always computed and compared.

Outputs (outputs/<run-id>/03_AHP_analysis/): see docs/DATA_DICTIONARY.md.
Usage: python code/03_AHP_analysis.py [--run-id ID] [--weights-source ...]
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fpv_calculations as K  # noqa: E402
import fpv_config as C  # noqa: E402
import fpv_utils as U   # noqa: E402


# =============================================================================== loading (cell 3)
def load_curated_inputs(log):
    """Read the five curated CSVs in the notebook's order; add Source_File; rename 'state' -> 'State'."""
    dfs = []
    for fname in C.CURATED_FILES:
        df = pd.read_csv(U.require(C.CURATED_DIR / fname))
        df["Source_File"] = fname
        log.info(f"loaded {fname}: {len(df)} rows x {df.shape[1] - 1} columns")
        dfs.append(df)
    df_integrated = pd.concat(dfs, ignore_index=True)
    # The curated files store an obsolete Capacity_Factor. It is replaced in memory by Eq. 3 (no performance
    # ratio); the input files are not changed. Deciles are scale-invariant, so categories and ranks are unaffected.
    m = K.fpv_metrics(df_integrated["surfaceArea_sqkm"], df_integrated["Annual_solar_potential"])
    K.assert_cf_follows_eq3(m["Capacity_Factor"], df_integrated["Annual_solar_potential"])
    df_integrated["Capacity_Factor"] = m["Capacity_Factor"]
    log.info("Capacity_Factor recalculated from Eq. 1-4 for all curated rows (stored column not used)")
    if "State" not in df_integrated.columns and "state" in df_integrated.columns:
        df_integrated = df_integrated.rename(columns={"state": "State"})   # header only; values untouched
    return df_integrated


# =============================================================================== de-duplication (cell 6)
def _normalize_state_for_matching(value, row_idx):
    if pd.isna(value) or str(value).strip() == "":
        return f"__MISSING_STATE_ROW_{row_idx}__"
    return str(value).strip().upper()


def normalize_ownership_label(token):
    key = token.strip().lower()
    canonical = {"federal": "Federal", "state": "State", "local": "Local Government",
                 "localgov": "Local Government", "local government": "Local Government", "county": "County",
                 "city": "City", "municipal": "Municipal", "tribe": "Tribal", "tribal": "Tribal",
                 "utility": "Public Utility", "publicutility": "Public Utility",
                 "public utility": "Public Utility", "private": "Private"}
    return canonical.get(key, token.strip().title())


def merge_ownership_categories(values):
    seen = {}
    for value in values:
        if pd.isna(value):
            continue
        for part in [p.strip() for p in str(value).replace(";", ",").split(",")]:
            if not part:
                continue
            label = normalize_ownership_label(part)
            if label.lower() not in seen:
                seen[label.lower()] = label
    return ", ".join(seen.values()) if seen else np.nan


def deduplicate(df_integrated, log):
    """Collapse rows with identical (Name, State) across ownership files (cell 6, logic unchanged)."""
    n_before = len(df_integrated)
    df_integrated["_State_match_key"] = [_normalize_state_for_matching(v, i)
                                         for i, v in df_integrated["State"].items()]
    df_integrated["_Dup_Key"] = list(zip(df_integrated["Name"], df_integrated["_State_match_key"]))
    state_by_key = df_integrated.groupby("_Dup_Key")["State"].first().to_dict()
    key_counts = df_integrated.groupby("_Dup_Key")["Source_File"].apply(list).reset_index()
    key_counts.columns = ["Dup_Key", "Source_Files"]
    key_counts["Occurrences"] = key_counts["Source_Files"].apply(len)
    dupes = key_counts[key_counts["Occurrences"] > 1]
    all_dupe_keys = set(dupes["Dup_Key"].tolist())
    df_integrated["Is_Duplicate"] = df_integrated["_Dup_Key"].isin(all_dupe_keys)

    own_orig = df_integrated.groupby("_Dup_Key")["Ownership"].apply(list).to_dict()
    own_merged = {k: merge_ownership_categories(v) for k, v in own_orig.items()}
    files_by_key = df_integrated.groupby("_Dup_Key")["Source_File"].apply(list).to_dict()

    df_deduped = (df_integrated.sort_values("Source_File")
                  .drop_duplicates(subset="_Dup_Key", keep="first")
                  .reset_index(drop=True))
    df_deduped["Ownership"] = df_deduped["_Dup_Key"].map(own_merged)
    assert df_deduped["_Dup_Key"].duplicated().sum() == 0

    report = pd.DataFrame([{"Name": k[0], "State": state_by_key.get(k), "Occurrences": len(files_by_key[k]),
                            "Source_Files": "; ".join(files_by_key[k]),
                            "Original_Ownership_Values": " | ".join(map(str, own_orig[k])),
                            "Merged_Ownership": own_merged[k]}
                           for k in sorted(all_dupe_keys, key=lambda k: (k[0], str(k[1])))])
    df_deduped = df_deduped.drop(columns=["_State_match_key", "_Dup_Key"])
    log.info(f"de-duplication by (Name, State): {n_before} rows -> {len(df_deduped)} "
             f"({len(all_dupe_keys)} sites appear in more than one ownership file)")
    return df_deduped, report


# =============================================================================== scores (cell 7)
def calculate_ownership_score(value):
    """Federal 5, State 4, Local/Tribal/County/City/Municipal 3, Utility 2, Private 1; summed, uncapped."""
    if pd.isna(value):
        return 0
    v = str(value).lower()
    score = 0
    if "federal" in v:
        score += 5
    if "state" in v:
        score += 4
    if any(w in v for w in ["local", "tribe", "tribal", "county", "city", "municipal"]):
        score += 3
    if "public utility" in v or "utility" in v:
        score += 2
    if "private" in v:
        score += 1
    return score


def assign_state_regulation_score(state):
    """Placeholder state table of the original code (its own docstring says so)."""
    if pd.isna(state):
        return C.STATE_SCORE_DEFAULT
    return C.STATE_SCORES.get(str(state).upper().strip(), C.STATE_SCORE_DEFAULT)


def add_scores(df):
    df["State_Score"] = df["State"].apply(assign_state_regulation_score)
    df["Ownership_Score"] = df["Ownership"].apply(calculate_ownership_score)
    df["OwnershipType"] = df["Ownership"]
    assert df.duplicated(subset=["Name", "State"]).sum() == 0
    for c in ["State_Score", "Ownership_Score"]:
        assert pd.api.types.is_numeric_dtype(df[c]) and np.isfinite(df[c]).all()
    return df


# =============================================================================== weights (cell 9)
def calculate_weights_from_pairwise_excel(matrix, criterion_names):
    """Principal-eigenvector weights and CR (notebook cell 9, logic unchanged)."""
    n = len(criterion_names)
    eigenvalues, eigenvectors = np.linalg.eig(matrix)
    idx = np.argmax(np.abs(eigenvalues.real))
    lambda_max = eigenvalues[idx].real
    v = eigenvectors[:, idx].real
    if v[0] < 0:
        v = -v
    weights_array = v / v.sum()
    weights = {name: abs(w) for name, w in zip(criterion_names, weights_array)}
    total = sum(weights.values())
    weights = {k: w / total for k, w in weights.items()}
    CI = (lambda_max - n) / (n - 1) if n > 1 else 0
    RI = C.RANDOM_INDEX.get(n, 1.49)
    CR = CI / RI if RI > 0 else 0
    return weights, CR, lambda_max


def matrix_to_model_order(df_pairwise):
    """Strip labels, map Excel criterion names to model variables, reorder to C.VARIABLES (cell 9)."""
    df_pairwise = df_pairwise.copy()
    df_pairwise.columns = [C.CRITERION_MAPPING.get(c, c) for c in df_pairwise.columns.str.strip()]
    df_pairwise.index = [C.CRITERION_MAPPING.get(i, i) for i in df_pairwise.index.str.strip()]
    missing = [v for v in C.VARIABLES if v not in df_pairwise.columns or v not in df_pairwise.index]
    if missing:
        raise ValueError(f"criteria missing from pairwise matrix: {missing}")
    m = df_pairwise.loc[C.VARIABLES, C.VARIABLES].values.astype(float)
    if np.isnan(m).any() or (m <= 0).any():
        raise ValueError("pairwise matrix contains NaN or non-positive entries")
    return m


def final_weight_check(weights):
    """Cell 9 tail: renormalise only if the sum is off by more than 0.001."""
    total = sum(weights.values())
    if abs(total - 1.0) > 0.001:
        weights = {k: v / total for k, v in weights.items()}
    return weights


def read_simulated_matrices(log):
    wb = openpyxl.load_workbook(U.require(C.SIMULATED_MATRICES_XLSX), read_only=True, data_only=True)
    summary = pd.DataFrame(list(wb["Summary"].iter_rows(values_only=True)))
    summary.columns = summary.iloc[0]
    summary = summary.iloc[1:].reset_index(drop=True)
    sheets = [s for s in wb.sheetnames if s not in ("Summary", "Template")]
    if len(sheets) != 100:
        raise ValueError(f"expected 100 simulated matrices, found {len(sheets)}")
    mats, meta = [], []
    for k, sh in enumerate(sheets):
        rows = list(wb[sh].iter_rows(values_only=True))
        header = [str(c).strip() for c in rows[1][1:10]]
        rowlab = [str(r[0]).strip().split("(")[0] for r in rows[2:11]]
        if header != C.EXCEL_CRITERIA_ORDER or rowlab != C.EXCEL_CRITERIA_ORDER:
            raise ValueError(f"unexpected criterion labels in sheet {sh}")
        A = np.array([[float(v) for v in r[1:10]] for r in rows[2:11]])
        if not (np.allclose(A * A.T, 1.0, atol=1e-9) and np.allclose(np.diag(A), 1.0)):
            raise ValueError(f"sheet {sh} is not a reciprocal unit-diagonal matrix")
        mats.append(A)
        meta.append({"sheet": sh, "stakeholder_field": summary.loc[k, "Stakeholder"],
                     "expert_no": summary.loc[k, "Expert"], "CR_saved_Summary": float(summary.loc[k, "CR"]),
                     "lambda_max_saved_Summary": float(summary.loc[k, "lambda_max"])})
    log.info(f"read {len(mats)} simulated matrices (all reciprocal, unit diagonal)")
    return np.stack(mats), pd.DataFrame(meta)


def aggregate_and_weigh(log, out):
    """Geometric mean of ALL 100 matrices; weights and CR; individual CRs; compare with CF438420."""
    mats, meta = read_simulated_matrices(log)
    crs = []
    for A in mats:
        _, cr, lam = calculate_weights_from_pairwise_excel(
            matrix_to_model_order(pd.DataFrame(A, index=C.EXCEL_CRITERIA_ORDER, columns=C.EXCEL_CRITERIA_ORDER)),
            C.VARIABLES)
        crs.append((cr, lam))
    meta["CR_recomputed"] = [c for c, _ in crs]
    meta["lambda_max_recomputed"] = [l for _, l in crs]
    meta["CR_ge_0.10"] = meta["CR_recomputed"] >= C.CR_THRESHOLD
    meta["included_in_aggregation"] = True          # M1: no CR-based exclusion
    meta.to_csv(out / "individual_matrix_CR.csv", index=False)
    n_hi = int(meta["CR_ge_0.10"].sum())
    log.info(f"individual CRs: <0.05: {(meta.CR_recomputed < 0.05).sum()}, 0.05-0.10: "
             f"{((meta.CR_recomputed >= 0.05) & (meta.CR_recomputed < 0.10)).sum()}, >=0.10: {n_hi} "
             f"(max {meta.CR_recomputed.max():.4f}); ALL 100 are aggregated")

    G = np.exp(np.log(mats).mean(axis=0))
    G_df = pd.DataFrame(G, index=C.EXCEL_CRITERIA_ORDER, columns=C.EXCEL_CRITERIA_ORDER)
    G_df.to_csv(out / "aggregated_matrix_geometric_mean_all100.csv")

    xls = pd.ExcelFile(U.require(C.AGGREGATED_MATRIX_XLSX))
    saved = pd.read_excel(C.AGGREGATED_MATRIX_XLSX, sheet_name=xls.sheet_names[0], index_col=0)
    saved.index, saved.columns = saved.index.str.strip(), saved.columns.str.strip()
    saved = saved.loc[C.EXCEL_CRITERIA_ORDER, C.EXCEL_CRITERIA_ORDER]
    max_diff = float(np.max(np.abs(G - saved.values.astype(float))))
    log.info(f"geometric mean of 100 vs CF438420.xlsx: max |diff| = {max_diff:.2e}")
    if max_diff > 1e-12:
        raise RuntimeError("recomputed aggregate does not match CF438420.xlsx; stopping")

    routes = {}
    for label, M in [("simulated_matrices", matrix_to_model_order(G_df)),
                     ("saved_aggregate", matrix_to_model_order(saved))]:
        w, cr, lam = calculate_weights_from_pairwise_excel(M, C.VARIABLES)
        routes[label] = (final_weight_check(w), cr, lam)
    return routes, max_diff, meta


# =============================================================================== categorisation (cell 12)
def categorize_variable(series, higher_is_better=True, is_binary=False):
    """1 (best) .. 10 (worst). Deciles for continuous variables; 1/10 for binary (cell 12, unchanged)."""
    if is_binary:
        mapping = {1: 1, 0: 10} if higher_is_better else {0: 1, 1: 10}
        return series.map(mapping).astype(int)
    if series.nunique(dropna=True) <= 1:
        return pd.Series(5, index=series.index, dtype=int)
    percentiles = [series.quantile(i / 10) for i in range(1, 10)]
    bins = [-np.inf] + percentiles + [np.inf]
    categories = pd.cut(series, bins=bins, labels=False, include_lowest=True, duplicates="drop")
    num_bins = categories.max() + 1
    if higher_is_better:
        if num_bins == 10:
            final = 10 - categories
        else:
            step = (10 - 1) / (num_bins - 1) if num_bins > 1 else 0
            final = (10 - (categories * step)).round().astype(int)
    else:
        if num_bins == 10:
            final = categories + 1
        else:
            step = (10 - 1) / (num_bins - 1) if num_bins > 1 else 0
            final = (1 + (categories * step)).round().astype(int)
    return final


def score_and_rank(df_work, weights):
    """Cells 13-14: weighted sum of categories (in C.VARIABLES order); rank method='min'; sort."""
    df = df_work.copy()
    df["AHP_Score"] = sum(df[f"{v}_category"] * weights[v] for v in C.VARIABLES)
    if "OwnershipType" not in df.columns:
        df["OwnershipType"] = df["Ownership"]
    df["Rank"] = df["AHP_Score"].rank(method="min")
    return df.sort_values("Rank").reset_index(drop=True)


# =============================================================================== diagnostics (cell 31)
def compute_vif(df_numeric):
    cols = df_numeric.columns.tolist()
    X_full = df_numeric.values.astype(float)
    n = X_full.shape[0]
    rec = []
    for i, col in enumerate(cols):
        y = X_full[:, i]
        X = np.column_stack([np.ones(n), np.delete(X_full, i, axis=1)])
        coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        ss_res = np.sum((y - X @ coef) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        rec.append({"Criterion": col, "R_squared": r2, "VIF": 1 / (1 - r2) if r2 < 1 else np.inf})
    return pd.DataFrame(rec).sort_values("VIF", ascending=False).reset_index(drop=True)


# =============================================================================== expert scenarios
def _parse_saaty_cell(v):
    if pd.isna(v):
        return np.nan
    if isinstance(v, str):
        v = v.strip()
        if "/" in v:
            num, den = v.split("/")
            return float(num) / float(den)
        return float(v)
    return float(v)


def read_expert_matrix(path):
    """Two-expert notebook cell 14: parse upper triangle, fill lower by reciprocity; no judgment changed."""
    raw = pd.read_excel(U.require(path), sheet_name=0, header=None)
    norm = lambda h: "State" if str(h).strip().startswith("State(") else str(h).strip()
    cols = [norm(h) for h in raw.iloc[1, 1:10].tolist()]
    rows = [norm(h) for h in raw.iloc[2:11, 0].tolist()]
    if cols != C.EXCEL_CRITERIA_ORDER or rows != C.EXCEL_CRITERIA_ORDER:
        raise ValueError(f"unexpected expert matrix labels in {path.name}")
    n = len(cols)
    mat = np.full((n, n), np.nan)
    for i in range(n):
        for j in range(n):
            mat[i, j] = _parse_saaty_cell(raw.iloc[2 + i, 1 + j])
    n_entered = int(np.sum(~np.isnan(mat)))
    for i in range(n):
        for j in range(n):
            if np.isnan(mat[i, j]):
                mat[i, j] = 1.0 / mat[j, i]
    return pd.DataFrame(mat, index=cols, columns=cols), n_entered


# =============================================================================== main
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-id", default=C.RUN_ID)
    ap.add_argument("--weights-source", choices=["simulated_matrices", "saved_aggregate"],
                    default="simulated_matrices",
                    help="simulated_matrices (default): geometric mean of all 100 matrices recomputed here; "
                         "saved_aggregate: CF438420.xlsx as read by the historical notebook")
    args = ap.parse_args()
    U.install_write_guard()
    out = U.stage_dir(args.run_id, 3)
    log = U.get_logger(out, "03_AHP_analysis")
    log.info("Pathway B: manually curated AHP candidate inputs (not regenerated from the 8,520 inventory)")

    # ---- inputs: hash before use -------------------------------------------------------------
    curated_paths = [C.CURATED_DIR / f for f in C.CURATED_FILES]
    hashes_before = {p.name: U.sha256(p) for p in curated_paths}

    # ---- 1. load + de-duplicate + scores ------------------------------------------------------
    df_integrated = load_curated_inputs(log)
    df_integrated.to_csv(out / "curated_inputs_concatenated_149.csv", index=False)
    df_dedup, dup_report = deduplicate(df_integrated, log)
    dup_report.to_csv(out / "dedup_report.csv", index=False)
    df_work = add_scores(df_dedup)

    # ---- 2. weights ---------------------------------------------------------------------------
    routes, agg_diff, cr_table = aggregate_and_weigh(log, out)
    weights, CR, lam = routes[args.weights_source]
    n = len(C.VARIABLES)
    log.info(f"weights source: {args.weights_source}; lambda_max = {lam:.6f}, CI = {(lam - n) / (n - 1):.6f}, "
             f"CR = {CR:.6f}")
    sorted_w = sorted(weights.items(), key=lambda x: x[1], reverse=True)
    pd.DataFrame([{"Criterion": k, "Weight": v, "Percentage": f"{v * 100:.2f}%"} for k, v in sorted_w]) \
        .to_csv(out / "ahp_weights_from_pairwise.csv", index=False)
    route_cmp = pd.DataFrame({lab: pd.Series(r[0]) for lab, r in routes.items()})
    route_cmp["abs_diff"] = (route_cmp["simulated_matrices"] - route_cmp["saved_aggregate"]).abs()
    route_cmp.index.name = "Criterion"
    route_cmp.to_csv(out / "weights_route_comparison.csv")
    pd.DataFrame([{"route": lab, "lambda_max": r[2], "CI": (r[2] - n) / (n - 1), "RI": C.RANDOM_INDEX[n],
                   "CR": r[1], "used": lab == args.weights_source,
                   "max_abs_diff_aggregate_vs_CF438420": agg_diff} for lab, r in routes.items()]) \
        .to_csv(out / "group_consistency.csv", index=False)

    # ---- 3. categorise, score, rank -------------------------------------------------------------
    missing_vars = [v for v in C.VARIABLES if v not in df_work.columns]
    if missing_vars:
        raise ValueError(f"required variables missing from curated inputs: {missing_vars}")
    for v in C.VARIABLES:
        df_work[f"{v}_category"] = categorize_variable(df_work[v], C.HIGHER_IS_BETTER[v], C.IS_BINARY[v])
    for c in ["Ownership_Score_category", "State_Score_category"]:
        assert df_work[c].between(1, 10).all()
    df_ranked = score_and_rank(df_work, weights)
    df_ranked.to_csv(out / "integrated_dam_rankings_ahp.csv", index=False)
    log.info(f"ranked {len(df_ranked)} sites; top 5: {df_ranked['Name'].head(5).tolist()}")

    # route sensitivity: ranks under the other weight route (reported, never used to override)
    other = "saved_aggregate" if args.weights_source == "simulated_matrices" else "simulated_matrices"
    alt = score_and_rank(df_work, routes[other][0])
    m = df_ranked[["Name", "State", "Rank", "AHP_Score"]].merge(
        alt[["Name", "State", "Rank", "AHP_Score"]], on=["Name", "State"], suffixes=("", f"_{other}"))
    m["rank_differs"] = m["Rank"] != m[f"Rank_{other}"]
    m["abs_score_diff"] = (m["AHP_Score"] - m[f"AHP_Score_{other}"]).abs()
    m.to_csv(out / "rank_route_comparison.csv", index=False)
    log.info(f"rank differences between weight routes: {int(m['rank_differs'].sum())}; "
             f"max |score diff| = {m['abs_score_diff'].max():.2e}")

    # ---- 4. manuscript-relevant summaries -------------------------------------------------------
    df_ranked[df_ranked["Rank"] <= C.TOP_N].to_csv(out / "top30_baseline.csv", index=False)
    src = df_ranked.groupby("Source_File")["AHP_Score"].agg(["mean", "min", "max", "count"])
    src.columns = ["Avg_Score", "Best_Score", "Worst_Score", "Count"]
    src.sort_values("Avg_Score").to_csv(out / "scores_by_source_file.csv")
    top30 = df_ranked[df_ranked["Rank"] <= C.TOP_N]
    top30["State"].value_counts().rename_axis("State").reset_index(name="Count") \
        .to_csv(out / "top30_state_counts.csv", index=False)                     # cells 25/27 (figure source)
    top30["OwnershipType"].value_counts().rename_axis("OwnershipType").reset_index(name="Count") \
        .to_csv(out / "top30_ownership_counts.csv", index=False)
    # Figure 4b counts owners, so multi-owner sites contribute once per owner
    (top30["OwnershipType"].str.split(",").explode().str.strip().value_counts().rename_axis("Owner")
     .reset_index(name="Count").to_csv(out / "top30_ownership_token_counts.csv", index=False))
    # FPV potential of the curated pool (same formula as Script 2; curated attributes used as-is)
    a_m2 = df_ranked["surfaceArea_sqkm"] * 1e6
    e_inc = C.F_COV * a_m2 * df_ranked["Annual_solar_potential"]
    v_evap = C.F_COV * a_m2 * df_ranked["Annual_evaporation"] * C.EVAP_SUPPRESSION_FRACTION
    gsl = df_ranked["Name"].str.strip().str.lower() == "great salt lake"
    cap_mw = K.fpv_metrics(df_ranked["surfaceArea_sqkm"], df_ranked["Annual_solar_potential"])["installed_capacity_MW"]
    pd.DataFrame([{"population": lab, "records": int(m.sum()), "installed_capacity_GW": cap_mw[m].sum() / 1e3,
                   "incident_solar_TWh_per_yr": e_inc[m].sum() / 1e9,
                   "electricity_TWh_per_yr": C.ETA * e_inc[m].sum() / 1e9,
                   "evap_reduction_upper_bound_km3_per_yr": v_evap[m].sum() / 1e9,
                   "evaporation_assumption": "100% PEV suppression (THEORETICAL UPPER BOUND)"}
                  for lab, m in [("curated pool (138)", pd.Series(True, index=df_ranked.index)),
                                 ("baseline Top-30", df_ranked["Rank"] <= C.TOP_N), ("Great Salt Lake", gsl)]]) \
        .to_csv(out / "curated_pool_fpv_totals.csv", index=False)
    contrib = df_ranked[["Name", "State", "Rank"]].copy()
    for v in C.VARIABLES:
        contrib[f"{v}_contribution"] = df_ranked[f"{v}_category"] * weights[v]
    contrib.to_csv(out / "criterion_contributions.csv", index=False)
    crit = df_ranked[[f"{v}_category" for v in C.VARIABLES]].copy()
    crit.columns = C.VARIABLES
    crit.corr(method="spearman").to_csv(out / "criteria_spearman_correlation.csv")
    compute_vif(crit).to_csv(out / "criteria_vif_table.csv", index=False)

    # ---- 5. real-expert comparison scenarios ----------------------------------------------------
    exp_rows = []
    for key, path in C.EXPERT_RAW.items():
        if not path.exists():
            log.warning(f"{key}: workbook not supplied; expert scenario skipped")
            continue
        mat, n_entered = read_expert_matrix(path)
        w, cr, lam_e = calculate_weights_from_pairwise_excel(matrix_to_model_order(mat), C.VARIABLES)
        tot = sum(w.values())
        if abs(tot - 1.0) > 1e-9:          # two-expert notebook cell 15
            w = {k: v / tot for k, v in w.items()}
        mat.to_csv(out / f"{key}_pairwise_matrix_reciprocal_filled.csv")
        pd.DataFrame([{"Criterion": k, "Weight": v} for k, v in w.items()]).to_csv(out / f"{key}_ahp_weights.csv",
                                                                                  index=False)
        score_and_rank(df_work, w).to_csv(out / f"{key}_integrated_dam_rankings_ahp.csv", index=False)
        exp_rows.append({"Expert": key.replace("_", " "), "Lambda_max": lam_e, "Consistency_Index_CI": (lam_e - n) / (n - 1),
                         "Random_Index_RI": C.RANDOM_INDEX[n], "Consistency_Ratio_CR": cr,
                         "CR_Threshold": C.CR_THRESHOLD, "Pass_Fail": "PASS" if cr <= C.CR_THRESHOLD else "FAIL",
                         "Judgments_entered": n_entered})
        log.info(f"{key}: CR = {cr:.4f} ({'PASS' if cr <= C.CR_THRESHOLD else 'FAIL'} at 0.10); "
                 f"comparison scenario only, not the baseline")
    if exp_rows:
        pd.DataFrame(exp_rows).to_csv(out / "expert_consistency_summary.csv", index=False)

    # ---- 6. input integrity -------------------------------------------------------------------
    hashes_after = {p.name: U.sha256(p) for p in curated_paths}
    if hashes_after != hashes_before:
        raise RuntimeError("curated input files changed during the run")
    log.info("curated input hashes unchanged after the run")

    U.write_manifest(out, "03_AHP_analysis.py",
                     curated_paths + [C.SIMULATED_MATRICES_XLSX, C.AGGREGATED_MATRIX_XLSX] +
                     [p for p in C.EXPERT_RAW.values() if p.exists()],
                     {"weights_source": args.weights_source, "variables": C.VARIABLES,
                      "higher_is_better": C.HIGHER_IS_BETTER, "is_binary": C.IS_BINARY,
                      "state_scores_placeholder": C.STATE_SCORES, "random_index": C.RANDOM_INDEX[n],
                      "n_matrices_aggregated": int(cr_table["included_in_aggregation"].sum()),
                      "n_matrices_CR_ge_0.10": int(cr_table["CR_ge_0.10"].sum()),
                      "group_CR": CR, "weights": weights},
                     ["Capacity_Factor recalculated from Eq. 1-4; the stored curated column is obsolete and unused.",
                      "All 100 simulated matrices aggregated (no CR exclusion, M1).",
                      "Curated inputs used as-is; not regenerated from the regional inventory.",
                      "State_Score uses the original placeholder table and the source state labels "
                      "(Washoe/Heron/Yellowstone mislabelled in the source; preserved, issue C9)."])
    log.info("done")


if __name__ == "__main__":
    main()
