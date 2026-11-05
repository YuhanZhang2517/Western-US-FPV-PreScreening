"""05 - Manuscript Figures 1, 3, 4 and 5, drawn from this run's outputs.

Drawing code is ported from AHP_modified_03_09.ipynb: cell 1 (Figure 1), cell 28 (Figure 3), cell 27 (Figure 4),
cell 18 large-text block (Figure 5). Figure 1 uses the corrected 8,516-record inventory.
Figure 2 needs a state-boundary layer that is not distributed; its data are in
04_sensitivity_analysis/figsrc_geographic_robustness.csv. Figure 6 is a screenshot of the Shiny application.

Outputs (outputs/<run-id>/05_figures/): figure1_surface_area_distribution, figure3_top5_contributions,
  figure4_top30_state_ownership, figure5_rank_uncertainty (.png and .pdf)
Usage: python code/05_figures.py [--run-id ID]
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import matplotlib.ticker as ticker       # noqa: E402
import numpy as np                       # noqa: E402
import pandas as pd                      # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fpv_config as C  # noqa: E402
import fpv_utils as U   # noqa: E402

CRITERION_LABELS = ["Annual Evaporation", "Ice", "Max Wind", "Distance to Transmission Line", "Solar Radiation",
                    "Capacity Factor", "Harmful Algal Bloom", "Ownership Score", "State Score"]
CLASS_COLORS = {"Highly Robust": "darkgreen", "Moderately Robust": "lightgreen", "Partially Robust": "orange",
                "Weight-Sensitive": "red"}
OWNER_COLORS = {"Private": "#DC143C", "Public Utility": "#FF8C00", "Local Government": "#9370DB",
                "State Government": "#4682B4", "Federal Government": "#2E8B57", "Tribal": "#8B4513"}
OWNER_LABELS = {"Private": "Private", "Utility": "Public Utility", "PublicUtility": "Public Utility",
                "Public Utility": "Public Utility", "LocalGov": "Local Government", "Local": "Local Government",
                "Local Government": "Local Government", "State": "State Government", "Federal": "Federal Government",
                "Tribal": "Tribal", "Tribe": "Tribal"}


def save(fig, out, name):
    fig.savefig(out / f"{name}.png", dpi=300, bbox_inches="tight")
    fig.savefig(out / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)


def figure1(inv, stats, out):
    """Surface-area histogram and cumulative area curve (cell 1)."""
    sa = (pd.to_numeric(inv["surfaceArea"]) * C.FIG1_ACRE_TO_M2).dropna()
    sa = sa[sa > 0]
    s = np.sort(sa.to_numpy())
    pct_res = np.arange(1, len(s) + 1) / len(s) * 100
    pct_area = np.cumsum(s[::-1]) / s.sum() * 100
    pct_large, area_large = stats["pct_records_gt_10km2"], stats["pct_area_in_gt_10km2"]
    blue, red, grey, mm = "#4878CF", "#D62728", "#888888", 1 / 25.4
    with plt.rc_context({"font.size": 7, "axes.labelsize": 8, "xtick.labelsize": 7, "ytick.labelsize": 7,
                         "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 0.5}):
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(180 * mm, 70 * mm))
        a1.hist(sa, bins=np.logspace(np.floor(np.log10(sa.min())), np.ceil(np.log10(sa.max())), 40), color=blue,
                edgecolor="white", linewidth=0.3)
        a1.set_xscale("log")
        a1.set_yscale("log")
        a1.set_xlabel("Surface area (m²)")
        a1.set_ylabel("Count")
        a1.axvline(C.FIG1_THRESHOLD_M2, color=red, linestyle="--", linewidth=0.7)
        a1.text(-0.18, 1.02, "a", transform=a1.transAxes, fontsize=8, fontweight="bold")
        a2.plot(pct_res, pct_area, color=blue, linewidth=1.0)
        a2.plot([0, 100], [0, 100], color=grey, linestyle="--", linewidth=0.6)
        a2.axvline(pct_large, color=red, linestyle="--", linewidth=0.7)
        a2.axhline(area_large, color=red, linestyle="--", linewidth=0.7)
        a2.annotate(f"{pct_large:.1f}% of reservoirs\n(>10 km²) hold\n{area_large:.0f}% of area",
                    xy=(pct_large, area_large), xytext=(pct_large + 6, max(area_large - 22, 10)), fontsize=6, color=red,
                    arrowprops=dict(arrowstyle="->", color=red, lw=0.5),
                    bbox=dict(boxstyle="square,pad=0.2", fc="white", ec="none", alpha=0.8))
        a2.set_xlabel("Cumulative % of reservoirs (largest first)")
        a2.set_ylabel("Cumulative % of total surface area")
        a2.set_xlim(0, 100)
        a2.set_ylim(0, 100)
        a2.xaxis.set_major_locator(ticker.MultipleLocator(20))
        a2.yaxis.set_major_locator(ticker.MultipleLocator(20))
        a2.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{int(x)}%"))
        a2.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{int(x)}%"))
        a2.text(-0.18, 1.02, "b", transform=a2.transAxes, fontsize=8, fontweight="bold")
        fig.tight_layout(pad=0.5, w_pad=4.0)
        save(fig, out, "figure1_surface_area_distribution")


def figure3(contrib, out):
    """Criterion contributions to the scores of the top five candidates (cell 28, stacked bars)."""
    top = contrib.sort_values("Rank").head(5)
    fig, ax = plt.subplots(figsize=(16, 10))
    bottom = np.zeros(len(top))
    for v, label, color in zip(C.VARIABLES, CRITERION_LABELS, plt.cm.tab10(np.linspace(0, 1, len(C.VARIABLES)))):
        vals = top[f"{v}_contribution"].to_numpy()
        ax.bar(np.arange(len(top)), vals, 0.6, bottom=bottom, label=label, color=color, edgecolor="black", linewidth=1.5)
        bottom += vals
    for i, total in enumerate(bottom):
        ax.text(i, total, f"{total:.2f}", ha="center", va="bottom", fontsize=14, fontweight="bold")
    ax.set_xticks(np.arange(len(top)))
    ax.set_xticklabels([n[:30] for n in top["Name"]], rotation=20, ha="right", fontsize=14)
    ax.set_xlabel("Reservoir", fontsize=16, fontweight="bold")
    ax.set_ylabel("AHP Score Contribution", fontsize=16, fontweight="bold")
    ax.legend(fontsize=12, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    save(fig, out, "figure3_top5_contributions")


def figure4(states, owners, out):
    """Top-30 state counts and owner counts (cell 27). Multi-owner sites count once per owner."""
    owners = owners.assign(Label=owners["Owner"].map(lambda o: OWNER_LABELS.get(o, o))).groupby("Label", sort=False)["Count"] \
        .sum().sort_values(ascending=False)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(32, 14))
    bars = a1.bar(range(len(states)), states["Count"], color=plt.cm.Set3(np.linspace(0, 1, len(states))),
                  edgecolor="black", linewidth=2, alpha=0.8)
    for bar, n in zip(bars, states["Count"]):
        a1.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), str(n), ha="center", va="bottom", fontsize=20,
                fontweight="bold")
    a1.set_xticks(range(len(states)))
    a1.set_xticklabels(states["State"], rotation=45, ha="right", fontsize=20)
    a1.tick_params(axis="y", labelsize=20)
    a1.set_xlabel("State", fontsize=22, fontweight="bold")
    a1.set_ylabel("Number of Top 30 Reservoirs", fontsize=22, fontweight="bold")
    a1.grid(True, axis="y", alpha=0.3, linestyle="--", linewidth=1)
    a1.set_axisbelow(True)
    total = owners.sum()
    a2.pie(owners.to_numpy(), labels=owners.index, colors=[OWNER_COLORS.get(k, "#FFD700") for k in owners.index],
           autopct=lambda p: f"{p:.1f}%\n({int(round(p / 100 * total))})", startangle=90, counterclock=False,
           wedgeprops=dict(edgecolor="black", linewidth=2.5), textprops=dict(fontsize=20, fontweight="bold"),
           pctdistance=0.75)
    a2.axis("equal")
    fig.tight_layout()
    save(fig, out, "figure4_top30_state_ownership")


def figure5(rob, sims, out):
    """Rank uncertainty (cell 18, large-text block)."""
    rob = rob.sort_values("Base_Rank")
    fig, axes = plt.subplots(2, 2, figsize=(36, 29))
    a1, a2, a3, a4 = axes.ravel()
    top50 = rob.head(50)
    for i, r in enumerate(top50.itertuples()):
        a1.plot([r.Rank_Min, r.Rank_Max], [i, i], linewidth=8, alpha=0.6, color="steelblue")
        a1.plot([r.Rank_Q25, r.Rank_Q75], [i, i], linewidth=12, alpha=0.9, color="navy")
        a1.scatter([r.Base_Rank], [i], s=100, c="red", marker="D", zorder=5, edgecolors="black", linewidth=1.5)
    a1.set_yticks(np.arange(len(top50)))
    a1.set_yticklabels([n[:30] for n in top50["Dam_Name"]], fontsize=15)
    a1.set_xlabel("Rank", fontsize=21, fontweight="bold")
    a1.set_ylabel("Reservoir", fontsize=21, fontweight="bold")
    a1.tick_params(axis="x", labelsize=16)
    a1.grid(True, alpha=0.3, axis="x")
    a1.invert_yaxis()
    top100 = rob.head(100)
    colors = ["darkgreen" if p >= .8 else "lightgreen" if p >= .5 else "orange" if p >= .2 else "red"
              for p in top100["Top30_Probability"]]
    a2.barh(range(len(top100)), top100["Top30_Probability"], color=colors, alpha=0.8, edgecolor="black", linewidth=0.5)
    for x, c, label in [(.8, "darkgreen", "P=0.8 (Robust)"), (.5, "orange", "P=0.5"), (.2, "red", "P=0.2 (Sensitive)")]:
        a2.axvline(x, color=c, linestyle="--", linewidth=2, label=label)
    a2.set_yticks(range(0, len(top100), 10))
    a2.set_yticklabels(range(1, len(top100) + 1, 10), fontsize=16)
    a2.set_xlabel("P(Top-30 Membership)", fontsize=21, fontweight="bold")
    a2.set_ylabel("Base Rank", fontsize=21, fontweight="bold")
    a2.tick_params(axis="x", labelsize=16)
    a2.legend(fontsize=15, loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0)
    a2.grid(True, alpha=0.3, axis="x")
    a2.invert_yaxis()
    for cls, color in CLASS_COLORS.items():
        sub = rob[rob["Robustness_Class"] == cls]
        a3.scatter(sub["Rank_IQR"], sub["Top30_Probability"], c=color, s=100, alpha=0.7, edgecolors="black", linewidth=1,
                   label=f"{cls} (n={len(sub)})")
    a3.axhline(.8, color="gray", linestyle="--", linewidth=1.5, alpha=0.5)
    a3.axvline(10, color="gray", linestyle="--", linewidth=1.5, alpha=0.5)
    a3.set_xlabel("Rank Interquartile Range (IQR)", fontsize=21, fontweight="bold")
    a3.set_ylabel("P(Top-30 Membership)", fontsize=21, fontweight="bold")
    a3.tick_params(axis="both", labelsize=16)
    a3.legend(fontsize=15, loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0)
    a3.grid(True, alpha=0.3)
    ex = pd.concat([rob[rob.Robustness_Class == "Highly Robust"].head(2), rob[rob.Robustness_Class == "Moderately Robust"].head(1),
                    rob[rob.Robustness_Class == "Weight-Sensitive"].head(2)])
    bp = a4.boxplot([sims.loc[sims["site_id"] == s, "rank"].to_numpy() for s in ex["Site_ID"]], positions=range(len(ex)),
                    orientation="vertical", patch_artist=True, widths=0.6)
    for patch, cls in zip(bp["boxes"], ex["Robustness_Class"]):
        patch.set_facecolor(CLASS_COLORS[cls])
        patch.set_alpha(0.7)
    a4.set_xticks(range(len(ex)))
    a4.set_xticklabels([f"{n[:20]}\n({c})" for n, c in zip(ex["Dam_Name"], ex["Robustness_Class"])], fontsize=15, rotation=30, ha="right")
    a4.set_ylabel("Rank", fontsize=21, fontweight="bold")
    a4.tick_params(axis="y", labelsize=16)
    a4.grid(True, alpha=0.3, axis="y")
    a4.invert_yaxis()
    fig.tight_layout(pad=3.5, w_pad=5.0, h_pad=4.5)
    save(fig, out, "figure5_rank_uncertainty")


def main():
    args = U.parse_args(__doc__.splitlines()[0])
    U.install_write_guard()
    run = C.OUTPUT_ROOT / args.run_id
    out = U.stage_dir(args.run_id, 5)
    log = U.get_logger(out, "05_figures")
    s1b, s2, s3, s4 = (run / C.STAGE_DIRS[k] for k in ("1b", 2, 3, 4))
    figure1(pd.read_csv(U.require(s2 / "regional_fpv_inventory_8516.csv"), low_memory=False),
            pd.read_csv(U.require(s1b / "figure1_statistics_8516.csv")).iloc[0], out)
    figure3(pd.read_csv(U.require(s3 / "criterion_contributions.csv")), out)
    figure4(pd.read_csv(U.require(s3 / "top30_state_counts.csv")),
            pd.read_csv(U.require(s3 / "top30_ownership_token_counts.csv")), out)
    figure5(pd.read_csv(U.require(s4 / "sensitivity_robustness_metrics.csv")),
            pd.read_csv(U.require(s4 / "sensitivity_all_simulations.csv.gz"), usecols=["site_id", "rank"]), out)
    log.info("figures 1, 3, 4 and 5 written")


if __name__ == "__main__":
    main()
