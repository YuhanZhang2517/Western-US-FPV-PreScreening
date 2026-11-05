"""Gate for the abandoned 0.8 performance ratio.

Static part: no active script may contain a performance-ratio term or a 0.8 outside the listed robustness uses.
Output part (when a run exists): every active Capacity_Factor equals G/8760.
Usage: python code/test_no_obsolete_performance_ratio.py [--run-id ID]
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fpv_config as C  # noqa: E402
import fpv_utils as U   # noqa: E402

ALLOWED = ("Top30_Probability", "pct_of_P>=0.8", "ROBUSTNESS_RULES", "n_P_top30_ge_0.8", "former 0.8", "obsolete 0.8", "0.8 performance",
           "abandoned 0.8", "P=0.8 (Robust)", "alpha=0.8", "hidden factor such as 0.8", "0.8 factor", "P >= 0.8", "P>=0.8")
FAILS = []


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def main():
    args = U.parse_args(__doc__.splitlines()[0])
    U.install_write_guard()
    term = re.compile(r"performance_?ratio\s*=|\*\s*0\.8\b|0\.8\s*\*|\bPR\s*=", re.I)
    point8 = re.compile(r"(?<![\d.])0\.8(?!\d)")
    for f in sorted(p for p in HERE.glob("*.py") if p.name != Path(__file__).name):
        for n, line in enumerate(f.read_text().splitlines(), 1):
            bad = term.search(line) and '"performance_ratio": "none"' not in line
            if bad or (point8.search(line) and not any(a in line for a in ALLOWED)):
                ok(False, f"{f.name}:{n}: {line.strip()}")
    ok(True, "static scan of active scripts finished")
    run = C.OUTPUT_ROOT / args.run_id
    pub = run / C.STAGE_DIRS[2] / "regional_fpv_inventory_8516.csv"
    if pub.exists():
        d = pd.read_csv(pub, float_precision="round_trip", low_memory=False)
        ok(float(np.abs(d.Capacity_Factor / (d.solar_kWhm2 / 8760) - 1).max()) < 1e-12, "regional Capacity_Factor = G/8760")
        ok(not any(c for c in d.columns if "0p8" in c or "performance" in c.lower()), "no obsolete CF column in the dataset")
        r = pd.read_csv(run / C.STAGE_DIRS[3] / "integrated_dam_rankings_ahp.csv", float_precision="round_trip")
        ok(float(np.abs(r.Capacity_Factor / (r.Annual_solar_potential / 8760) - 1).max()) < 1e-12, "AHP Capacity_Factor = G/8760")
    print(f"\n{len(FAILS)} failure(s)")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
