"""04 - Monte Carlo weight-sensitivity analysis, robustness classes and Mann-Whitney comparisons (Pathway B).

Historical source: Roadmap/AHP_modified_03_09.ipynb (version A producer)
  cell 18  10,000 simulations, +/-50 % uniform perturbation, seed 42, floor 0.01, renormalise;
           P(Top-30), rank statistics, robustness classes; saves robustness metrics, weight statistics,
           all simulations
  cell 19  manuscript Table 3: Highly Robust vs Weight-Sensitive Mann-Whitney U + rank-biserial r
           (printed only in the original; saved here as table3_HR_vs_WS.csv - same computation)
  cells 20-22  manuscript summary statistics       cell 23  Top-30 stability, Top-30 vs Rest test, transitions
  cell 24  table2_mannwhitney_{main,supplementary}.csv/.tex (Top-30 vs Rest; NOT manuscript Table 3)
and the expert Monte Carlo of AHP_modified_03_09_two_experts.ipynb cell 20 (same algorithm, seed, thresholds).

The perturbation loop is vectorised; the random-number stream (simulation-major, then the nine
criteria in model order), the floor, the left-to-right summation order and rank(method='min') are
preserved so that every simulated rank and score equals the original loop's value.

Input: outputs/<run-id>/03_AHP_analysis/ (baseline rankings, weights, expert weights)
Usage: python code/04_sensitivity_analysis.py [--run-id ID] [--skip-experts]
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu, rankdata

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fpv_config as C  # noqa: E402
import fpv_utils as U   # noqa: E402

V = C.VARIABLES


def read_exact(path):
    """Read a stage-3 CSV with round-trip float parsing (pandas' default parser can be off by 1 ulp)."""
    return pd.read_csv(path, float_precision="round_trip")


def read_weights(path):
    """Weights as np.float64, the type the original notebook held in memory."""
    return {k: np.float64(v) for k, v in read_exact(path).set_index("Criterion")["Weight"].items()}


def make_site_id(df):
    """Cell 18: Hylak_id if present, else Name__State, else Name__row_i."""
    if "Hylak_id" in df.columns:
        return df["Hylak_id"].astype(str)
    if "State" in df.columns:
        return df["Name"].astype(str).str.strip() + "__" + df["State"].astype(str).str.strip()
    return df["Name"].astype(str).str.strip() + "__row_" + df.index.astype(str)


def run_monte_carlo(df_ranked, weights, n_sim=C.N_SIMULATIONS, seed=C.RANDOM_SEED):
    """Return (normalised weights [n_sim x 9], scores [n_sim x n_sites], ranks [n_sim x n_sites]).

    Equivalent to cell 18: for each simulation, for each criterion in order,
    w' = max(0.01, w * (1 + U(-0.5, 0.5))); w' /= sum(w'); score = sum_k cat_k * w'_k; rank(method='min').
    """
    np.random.seed(seed)                                         # cell 18: np.random.seed(42)
    draws = np.random.uniform(-C.PERTURBATION_FACTOR, C.PERTURBATION_FACTOR, size=(n_sim, len(V)))
    base = np.array([weights[v] for v in V])
    W = np.maximum(C.WEIGHT_FLOOR, base[None, :] * (1 + draws))
    # The original renormalised with built-in sum() over np.float64 dict values. np.float64 is not an
    # exact Python float, so CPython adds them left to right without compensated summation.
    total = np.zeros(n_sim)
    for j in range(len(V)):
        total = total + W[:, j]
    Wn = W / total[:, None]
    cats = np.stack([df_ranked[f"{v}_category"].to_numpy() for v in V], axis=1)   # sites x 9
    S = np.zeros((n_sim, len(df_ranked)))
    for j in range(len(V)):                                      # sum(cat * w for var in variables)
        S = S + cats[None, :, j] * Wn[:, j][:, None]
    R = rankdata(S, method="min", axis=1).astype(float)          # Series.rank(method='min')
    return Wn, S, R


def classify(p, iqr):
    for name, p_min, iqr_max in C.ROBUSTNESS_RULES:
        if p >= p_min and (iqr_max is None or iqr <= iqr_max):
            return name
    return C.ROBUSTNESS_DEFAULT


def robustness_metrics(df_ranked, S, R, n_sim, full=True):
    """Cell 18 metric block (full=True) or the reduced expert-notebook column set (full=False)."""
    rows = []
    site_ids = df_ranked["Site_ID"].to_numpy()
    for site_id in df_ranked["Site_ID"].unique():
        cols = np.where(site_ids == site_id)[0]          # original filters all simulation rows by site_id
        base_row = df_ranked.iloc[cols[0]]
        ranks, scores = R[:, cols].ravel(), S[:, cols].ravel()
        p = (ranks <= C.TOP_N).sum() / n_sim
        q25, q75 = np.percentile(ranks, 25), np.percentile(ranks, 75)
        iqr = q75 - q25
        rec = {"Dam_Name": base_row["Name"], "Site_ID": site_id, "State": base_row["State"],
               "Base_Rank": base_row["Rank"], "Base_Score": base_row["AHP_Score"]}
        if full:
            rec.update({"Mean_Rank": np.mean(ranks), "Median_Rank": np.median(ranks), "Rank_Std": np.std(ranks),
                        "Rank_Min": np.min(ranks), "Rank_Max": np.max(ranks),
                        "Rank_Range": np.max(ranks) - np.min(ranks), "Rank_IQR": iqr, "Rank_Q25": q25,
                        "Rank_Q75": q75, "Top30_Probability": p, "Score_Mean": np.mean(scores),
                        "Score_Std": np.std(scores), "Robustness_Class": classify(p, iqr)})
        else:
            rec.update({"Rank_Min": ranks.min(), "Rank_Max": ranks.max(), "Rank_Q25": q25, "Rank_Q75": q75,
                        "Rank_IQR": iqr, "Top30_Probability": p, "Robustness_Class": classify(p, iqr)})
        rows.append(rec)
    df = pd.DataFrame(rows).sort_values("Base_Rank")
    return df if full else df.reset_index(drop=True)


def mann_whitney_table(g1, g2, label1, label2, with_r):
    """Two-sided scipy mannwhitneyu per criterion category; r = 1 - 2U/(n1 n2) (cell 19)."""
    rows = []
    for v in V:
        a, b = g1[f"{v}_category"], g2[f"{v}_category"]
        stat, p = mannwhitneyu(a, b, alternative="two-sided")
        rec = {"Criterion": v.replace("_", " "), f"{label1}_Median": a.median(), f"{label2}_Median": b.median()}
        if with_r:
            rec["Effect_Size_r"] = 1 - (2 * stat) / (len(a) * len(b))
        rec.update({"U_Statistic": stat, "P_Value": p, "Significant": "Yes" if p < 0.05 else "No",
                    f"n_{label1}": len(a), f"n_{label2}": len(b)})
        rows.append(rec)
    return pd.DataFrame(rows).sort_values("P_Value")


DISPLAY = {"Annual evaporation": "Annual Evaporation", "Ice binary": "Ice (Binary)", "Capacity Factor": "Capacity Factor",
           "log Annual solar GWh": "Log Annual Solar (GWh)", "State Score": "State Environmental Regulation",
           "HAB flag 20k": "Harmful Algal Bloom Flag", "Ownership Score": "Ownership",
           "nearest dist m": "Distance to Transmission Line", "max wind ms": "Maximum Wind Speed"}


def write_table2(df_sig, out):
    """Cell 24 exports (Top-30 vs Rest); file names kept for traceability. NOT manuscript Table 3."""
    t = df_sig.drop(columns=["n_Top30", "n_Rest"]).copy()
    t["P_Value_Display"] = t["P_Value"].apply(lambda p: "<0.001" if p < 0.001 else f"{p:.3f}")
    t["Criterion"] = t["Criterion"].replace(DISPLAY)
    t = t.rename(columns={"Top30_Median": "Top-30 Median", "Rest_Median": "Rest Median", "P_Value_Display": "p-value"})
    main = t[["Criterion", "Top-30 Median", "Rest Median", "p-value"]]
    main.to_csv(out / "table2_mannwhitney_main.csv", index=False)
    t.rename(columns={"U_Statistic": "U Statistic", "P_Value": "Raw p-value"})[
        ["Criterion", "Top-30 Median", "Rest Median", "U Statistic", "Raw p-value", "Significant"]
    ].to_csv(out / "table2_mannwhitney_supplementary.csv", index=False)
    lines = [r"\begin{table}[h]", r"\centering",
             r"\caption{Mann-Whitney U test results comparing Top-30 and remaining candidate water bodies across "
             r"screening criteria (categories: 1 = best, 10 = worst).}",
             r"\label{tab:mannwhitney}", r"\begin{tabular}{lccc}", r"\hline",
             r"Criterion & Top-30 Median & Rest Median & $p$-value \\", r"\hline"]
    for _, row in main.iterrows():
        lines.append(f"{row['Criterion']} & {row['Top-30 Median']:.1f} & {row['Rest Median']:.1f} & ${row['p-value']}$ \\\\")
    lines += [r"\hline", r"\end{tabular}", r"\end{table}"]
    with open(out / "table2_mannwhitney.tex", "x") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-id", default=C.RUN_ID)
    ap.add_argument("--skip-experts", action="store_true", help="skip the two real-expert Monte Carlo scenarios")
    args = ap.parse_args()
    U.install_write_guard()
    src = U.stage_dir(args.run_id, 3, create=False)
    out = U.stage_dir(args.run_id, 4)
    log = U.get_logger(out, "04_sensitivity_analysis")

    rank_path = U.require(src / "integrated_dam_rankings_ahp.csv")
    w_path = U.require(src / "ahp_weights_from_pairwise.csv")
    df_ranked = read_exact(rank_path)
    weights = read_weights(w_path)
    df_ranked["Site_ID"] = make_site_id(df_ranked)
    if df_ranked["Site_ID"].nunique() != len(df_ranked):
        log.warning("duplicate Site_IDs present (kept, as in the original)")
    n_sim = C.N_SIMULATIONS
    log.info(f"baseline: {len(df_ranked)} sites; {n_sim} simulations, +/-{C.PERTURBATION_FACTOR:.0%}, "
             f"seed {C.RANDOM_SEED}, floor {C.WEIGHT_FLOOR}")

    # ---- 1. Monte Carlo (cell 18) -----------------------------------------------------------
    Wn, S, R = run_monte_carlo(df_ranked, weights)
    n_sites = len(df_ranked)
    sims = pd.DataFrame({"simulation_id": np.repeat(np.arange(n_sim), n_sites),
                         "site_id": np.tile(df_ranked["Site_ID"].to_numpy(), n_sim),
                         "dam_name": np.tile(df_ranked["Name"].to_numpy(), n_sim),
                         "state": np.tile(df_ranked["State"].to_numpy(), n_sim),
                         "rank": R.ravel(), "ahp_score": S.ravel()})
    sims.to_csv(out / "sensitivity_all_simulations.csv.gz", index=False, compression="gzip")
    df_w = pd.DataFrame(Wn, columns=V)
    df_w.describe().to_csv(out / "sensitivity_weight_statistics.csv")

    df_rob = robustness_metrics(df_ranked, S, R, n_sim)
    df_rob.to_csv(out / "sensitivity_robustness_metrics.csv", index=False)
    counts = df_rob["Robustness_Class"].value_counts()
    log.info("robustness classes: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    summ = counts.reset_index()
    summ.columns = ["Robustness_Class", "Count"]
    summ["Percentage"] = (summ["Count"] / len(df_rob) * 100).round(1)
    summ.to_csv(out / "robustness_class_summary.csv", index=False)

    # ---- 2. manuscript Table 3: Highly Robust vs Weight-Sensitive (cell 19) -----------------
    rs = df_ranked.merge(df_rob[["Dam_Name", "Robustness_Class"]], left_on="Name", right_on="Dam_Name")
    hr = rs[rs["Robustness_Class"] == "Highly Robust"]
    ws = rs[rs["Robustness_Class"] == "Weight-Sensitive"]
    t3 = mann_whitney_table(hr, ws, "Robust", "Sensitive", with_r=True)
    t3.to_csv(out / "table3_HR_vs_WS.csv", index=False)
    log.info(f"Table 3 (manuscript): Highly Robust n={len(hr)} vs Weight-Sensitive n={len(ws)}")

    # ---- 3. summary statistics for the manuscript text (cells 20-22, 18 summary) --------------
    hr80 = df_rob[df_rob["Top30_Probability"] >= 0.8]
    traits = {v: 0 for v in V}
    for name in hr80["Dam_Name"]:
        row = df_ranked[df_ranked["Name"] == name].iloc[0]
        for v in V:
            if row[f"{v}_category"] <= 2:
                traits[v] += 1
    stats = [("n_sites", len(df_rob)), ("n_P_top30_ge_0.8", len(hr80)),
             ("n_P_top30_lt_0.2", int((df_rob["Top30_Probability"] < 0.2).sum())),
             ("n_Rank_IQR_le_10", int((df_rob["Rank_IQR"] <= 10).sum())),
             ("median_Rank_IQR_all", df_rob["Rank_IQR"].median()),
             ("median_Rank_IQR_Highly_Robust", df_rob.loc[df_rob.Robustness_Class == "Highly Robust", "Rank_IQR"].median()),
             ("median_Rank_IQR_Weight_Sensitive", df_rob.loc[df_rob.Robustness_Class == "Weight-Sensitive", "Rank_IQR"].median()),
             ("mean_P_top30_of_baseline_top30", df_rob.head(30)["Top30_Probability"].mean())]
    stats += [(f"pct_of_P>=0.8_sites_with_{v}_category<=2", traits[v] / len(hr80) * 100) for v in V]
    pd.DataFrame(stats, columns=["Statistic", "Value"]).to_csv(out / "manuscript_summary_statistics.csv", index=False)

    # ---- 4. Top-30 analyses (cell 23) and Table-2 exports (cell 24) ---------------------------
    top30 = df_rob[df_rob["Base_Rank"] <= 30].copy()
    stab = []
    for dam in top30["Dam_Name"]:
        cols = np.where(df_ranked["Name"].to_numpy() == dam)[0]   # cell 23 selects by dam_name
        r = R[:, cols].ravel()
        stab.append({"Dam_Name": dam, "Base_Rank": top30.loc[top30.Dam_Name == dam, "Base_Rank"].iloc[0],
                     "Pct_Top10": (r <= 10).sum() / n_sim, "Pct_Top30": (r <= 30).sum() / n_sim,
                     "Pct_Dropped": (r > 30).sum() / n_sim})
    pd.DataFrame(stab).sort_values("Base_Rank").to_csv(out / "top30_stability.csv", index=False)
    top30["Group"] = np.select([top30.Top30_Probability > 0.95,
                                (top30.Top30_Probability >= 0.5) & (top30.Top30_Probability <= 0.8),
                                top30.Top30_Probability < 0.5], ["consensus (P>0.95)", "borderline (0.5<=P<=0.8)",
                                                                  "vulnerable (P<0.5)"], default="other")
    top30[["Dam_Name", "Base_Rank", "Top30_Probability", "Rank_IQR", "Group"]].to_csv(
        out / "top30_consensus_groups.csv", index=False)
    sig = mann_whitney_table(df_ranked[df_ranked.Rank <= 30], df_ranked[df_ranked.Rank > 30], "Top30", "Rest",
                             with_r=False)
    sig.to_csv(out / "top30_vs_rest_mannwhitney_full.csv", index=False)
    write_table2(sig, out)
    edges, labels = [0, 10, 20, 30, 150], ["1-10", "11-20", "21-30", "31+"]
    tm = pd.DataFrame(0.0, index=labels, columns=labels)
    names = df_ranked["Name"].to_numpy()
    for i, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        tier = df_ranked[(df_ranked.Rank > lo) & (df_ranked.Rank <= hi)]
        for dam in tier["Name"]:
            r = R[:, np.where(names == dam)[0]].ravel()
            for j, (dlo, dhi) in enumerate(zip(edges[:-1], edges[1:])):
                tm.iloc[i, j] += ((r > dlo) & (r <= dhi)).sum()
        if len(tier):
            tm.iloc[i, :] = tm.iloc[i, :] / (len(tier) * n_sim) * 100
    tm.to_csv(out / "rank_transition_matrix_pct.csv")

    # ---- 5. figure-source tables (figures themselves are not regenerated) ---------------------
    geo = df_ranked[["Site_ID", "Name", "State", "latitude", "longitude", "Rank"]].merge(
        df_rob[["Site_ID", "Top30_Probability", "Rank_IQR", "Robustness_Class"]], on="Site_ID", how="left")
    geo.to_csv(out / "figsrc_geographic_robustness.csv", index=False)
    ex = pd.concat([df_rob[df_rob.Robustness_Class == "Highly Robust"].head(2),
                    df_rob[df_rob.Robustness_Class == "Moderately Robust"].head(1),
                    df_rob[df_rob.Robustness_Class == "Weight-Sensitive"].head(2)])
    sid = df_ranked["Site_ID"].tolist()
    pd.DataFrame([{"Site_ID": s, "Dam_Name": d, "Robustness_Class": c,
                   **{f"q{q}": np.percentile(R[:, sid.index(s)], q) for q in (0, 5, 25, 50, 75, 95, 100)}}
                  for s, d, c in ex[["Site_ID", "Dam_Name", "Robustness_Class"]].itertuples(index=False)]) \
        .to_csv(out / "figsrc_rank_distribution_examples.csv", index=False)
    contrib = []
    for s in df_rob[df_rob.Robustness_Class == "Highly Robust"].head(10)["Site_ID"]:
        row = df_ranked[df_ranked.Site_ID == s].iloc[0]
        contrib += [{"Site_ID": s, "Dam": row["Name"][:25], "Criterion": v.replace("_", " "),
                     "Contribution": row[f"{v}_category"] * weights[v]} for v in V]
    pd.DataFrame(contrib).to_csv(out / "figsrc_criterion_contributions_highly_robust.csv", index=False)

    # ---- 6. real-expert Monte Carlo (two-expert notebook cell 20) -----------------------------
    exp_inputs = []
    if not args.skip_experts:
        for key in C.EXPERT_RAW:
            if not (src / f"{key}_ahp_weights.csv").exists():
                log.warning(f"{key}: no expert weights; scenario skipped")
                continue
            p = U.require(src / f"{key}_ahp_weights.csv")
            q = U.require(src / f"{key}_integrated_dam_rankings_ahp.csv")
            exp_inputs += [p, q]
            we = read_weights(p)
            dr = read_exact(q)
            dr["Site_ID"] = make_site_id(dr)
            _, Se, Re = run_monte_carlo(dr, we)        # independent RandomState(42) stream per expert
            rob = robustness_metrics(dr, Se, Re, n_sim, full=False)
            rob.to_csv(out / f"{key}_sensitivity_robustness_metrics.csv", index=False)
            log.info(f"{key} robustness classes: " + ", ".join(
                f"{k} {v}" for k, v in rob["Robustness_Class"].value_counts().items()))

    U.write_manifest(out, "04_sensitivity_analysis.py", [rank_path, w_path] + exp_inputs,
                     {"n_simulations": n_sim, "perturbation_factor": C.PERTURBATION_FACTOR, "seed": C.RANDOM_SEED,
                      "weight_floor": C.WEIGHT_FLOOR, "top_n": C.TOP_N, "robustness_rules": C.ROBUSTNESS_RULES,
                      "mann_whitney": "scipy.stats.mannwhitneyu two-sided, default method",
                      "effect_size": "rank-biserial r = 1 - 2U1/(n1 n2)"},
                     ["table3_HR_vs_WS.csv = manuscript Table 3 (original printed it only).",
                      "table2_mannwhitney_* = Top-30 vs Rest (saved by the original; a different test, not Table 3).",
                      "Weight-Sensitive = P(Top-30) < 0.2 only (code rule; Appendix E wording differs, issue C11)."])
    log.info("done")


if __name__ == "__main__":
    main()
