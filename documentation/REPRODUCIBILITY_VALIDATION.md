# Reproducibility validation

**Tested 2026-11-04:** a copy of only the files in this repository, a new virtual environment built from `requirements.txt`, Python 3.14.7, Linux, a stripped environment with an empty home folder, and the commands in `README.md`.

| Test | Result |
|---|---|
| `./run_workflow.sh` | Completes in about 30 s using about 1 GB; validator reports 0 failures |
| Run with the final dataset, `ahp_candidates_138.csv` and all of `results/` deleted first | Completes; outputs byte-identical to the normal run, so results are computed and not copied |
| Corrected Flatiron area changed from 45 to 47 acres | Totals change and the validator fails, so the correction is live and the check is sensitive |
| Optional raw NID and transmission mode | Completes; 0 failures; final dataset byte-identical to the default run |
| System-call trace of the default run | No access to the authors' project folders |
| 8,516 records, all with calculated CF | Confirmed |
| CF = G/8760 for every record; no 0.8 factor | Confirmed |
| Flatiron Dam uses 45 acres; source value retained | Confirmed |
| Every other input attribute equals the approved inventory | Confirmed |
| Regional totals rebuilt from input files alone | Confirmed: 497.07 TWh/yr, 3.5213 km³/yr |
| State sums equal regional totals | Confirmed |
| 138 candidates, ranks, categories, classes | Match reference |
| AHP, Monte Carlo and Table 2–3 outputs | Byte-identical to version 2 |

## Reproducibility by step

| Step | Level |
|---|---|
| NID filtering | Reproducible with the separately obtained raw file; otherwise from processed inputs |
| Duplicate detection, manual keeps | Fully reproducible |
| Flatiron area correction | Fully reproducible from the corrections table; the choice of value is an author decision |
| ERA5 values | From processed grids; raw-to-grid rebuilt separately (optional script) to within 2.3e-6 in the 2026-11-03 audit; not repeated for this release |
| FPV area, capacity, electricity, CF, evaporation, state totals | Fully reproducible from the included inputs |
| Transmission distance | Reproducible with the separately obtained file; otherwise from processed inputs |
| 13 natural lakes | Processed inputs only |
| Curated 138 candidates | Processed inputs only; manual curation is not reproducible |
| 9 AHP indicators | Scores reproducible; HAB and ice inputs are processed values |
| 100 matrices | Aggregation reproducible; generation not |
| Weights, CR, scores, ranks | Fully reproducible from the included inputs |
| Monte Carlo, classes, Tables 2 and 3 | Fully reproducible with seed 42 |
| Expert scenarios (Appendix C) | Not reproducible here: workbooks not distributed |
| Figures 1, 3, 4, 5 | Drawn by `05_figures.py`; layout may differ slightly from the manuscript versions |
| Figure 2 | Data reproducible; drawing needs a state boundary layer and the older notebook |
| Figure 6 | Screenshot of the Shiny application, which is not in this repository |
