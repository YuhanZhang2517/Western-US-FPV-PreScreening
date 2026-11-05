# Western U.S. FPV pre-screening

Code and data for **"A customizable pre-screening framework for floating photovoltaic site scaling across western U.S. water bodies"** (Zhang, Lang, Lall).

The framework screens water bodies in eleven western U.S. states for floating photovoltaic (FPV) potential. It compiles a regional database, then uses the Analytic Hierarchy Process (AHP) and Monte Carlo sensitivity analysis to show how candidate rankings depend on criterion weights. It is a first-pass screening tool, not a project feasibility assessment.

> **Read `documentation/KNOWN_LIMITATIONS.md` before using the numbers.** Regional totals are theoretical. They include repeated reservoir area: removing structures that NID marks as associated would lower them to about 429 TWh/yr and 2.99 km³/yr. Evaporation is an upper bound, not realized water savings.

## Two analysis pathways

| | Regional pathway | AHP pathway |
|---|---|---|
| Population | **8,516 records** | **138 manually curated candidates** |
| Purpose | Theoretical capacity, electricity, capacity factor, evaporation | Screening scores, ranks, robustness |
| Main inputs | National Inventory of Dams (NID), 13 National Hydrography Dataset (NHD) lakes, ERA5 grids | Five curated Top-30 files, 100 simulated Saaty matrices |
| Scripts | 01, 01b, 02 | 03, 04 |

The pathways are independent: the 138 candidates are **not** generated from the 8,516 records, and 8 of them are not in the regional inventory.

## Repository structure

```text
code/                     workflow scripts and modules (keep together: imports are local)
data/regional/            regional_fpv_inventory_8516.csv, ERA5 grids, inputs, review files
data/regional/corrections/  approved surface-area corrections
data/ahp/                 ahp_candidates_138.csv, curated Top-30 files, matrices
data/metadata/            data dictionary and file manifest
results/reference/        reference outputs used by the validator
results/figures/          Figures 1, 3, 4 and 5
documentation/            sources, methods, validation, limitations, version history
run_workflow.sh           runs the workflow and all checks
```

**Older files:** `AHP_modified_03_09.ipynb` and the files directly under `data/` date from March 2026. They are kept for history and are superseded, and they contain the uncorrected Flatiron area. Use the folders above. The notebook still holds the Figure 2 map code.

## Data sources

NID (U.S. Army Corps of Engineers), NHD, ERA5 2020–2024 (Copernicus), HIFLD transmission lines and CyAN bloom data. Details and download notes: `documentation/DATA_SOURCES.md`. Field definitions: `data/metadata/DATA_DICTIONARY.md`.

| File | Content |
|---|---|
| `data/regional/regional_fpv_inventory_8516.csv` | Final corrected regional dataset: inputs plus FPV area, installed capacity, electricity, capacity factor, evaporation |
| `data/ahp/ahp_candidates_138.csv` | The 138 candidates with indicators, 1–10 scores, composite score and rank |
| `data/ahp/curated_top30/*.csv` | Original curated inputs. Their stored `Capacity_Factor` is obsolete and is recalculated by the code |
| `data/ahp/matrices/` | All 100 simulated pairwise matrices and their aggregate |

## The 8,516-record inventory

An earlier inventory had 8,520 records: 8,507 NID records and 13 lakes. Exact matching on normalized name, state and area found 7 groups. Three were verified as distinct reservoirs and kept (`MANUAL_KEEP` in `code/reservoir_duplicate_review.py`), and 4 records were removed. Dam structures with different names, such as dikes, are not removed by this rule, so 8,516 is a record count and not a verified count of distinct water bodies.

## Flatiron Dam area correction

NID reports 381,500 acres for Flatiron Dam (CO01654), about 8,000 times its published size. The authors corrected it to **45 acres**, the Reclamation 2012 survey value. The change is stored in `data/regional/corrections/surface_area_corrections.csv` and applied by `01b_deduplication.py` after the duplicate review is verified. The source value is kept in `surfaceArea_source_acres`, and files under `data/regional/review/` and `historical_inputs/` deliberately stay uncorrected. See `documentation/VERSION_HISTORY.md`.

## Calculations

These follow manuscript Eq. 1–4 (`code/fpv_calculations.py`). A is surface area and G is mean annual ERA5 irradiation in kWh m⁻² yr⁻¹.

| Quantity | Formula |
|---|---|
| FPV area | A_FPV = 0.10 × A |
| Incident solar energy | E_solar = G × A_FPV |
| Annual electricity | E_annual = 0.10 × E_solar |
| Installed capacity | P = 100 MW km⁻² × A_FPV |
| Capacity factor | CF = E_annual / (P × 8760) |
| Evaporation reduction | V = 0.10 × A × PEV (ERA5 potential evaporation) |

With these constants area cancels, so CF = G/8760. No performance ratio is applied: an earlier 0.8 factor was abandoned. CF is a theoretical resource measure, not observed performance. More detail: `documentation/METHODOLOGY.md`.

## Install

Tested with Python 3.14.7 on Linux.

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
./run_workflow.sh
```

Outputs go to `outputs/run/`. The workflow takes about a minute and about 1 GB of memory. To use a specific interpreter, set it first: `PYTHON=venv/bin/python ./run_workflow.sh`. Output folders are never overwritten, so use a new name for a repeat run: `./run_workflow.sh run2`.

| Step | Script | Result | Main outputs in `outputs/run/` |
|---:|---|---|---|
| 1 | `01_data_preparation.py` | 8,520-record inventory | `01_data_preparation/inventory_8520.gpkg` |
| 2 | `01b_deduplication.py` | Duplicate review, manual keeps, area correction, 8,516 records | `01b_deduplication/inventory_8516.gpkg`, `surface_area_corrections_applied.csv` |
| 3 | `02_data_processing.py` | Site-level and state-level regional results | `02_data_processing/regional_fpv_inventory_8516.csv`, `regional_totals.csv`, `regional_state_totals.csv` |
| 4 | `03_AHP_analysis.py` | Weights, consistency, scores, ranks | `03_AHP_analysis/integrated_dam_rankings_ahp.csv` |
| 5 | `04_sensitivity_analysis.py` | Monte Carlo (10,000 runs, seed 42), robustness classes, Tables 2 and 3 | `04_sensitivity_analysis/sensitivity_robustness_metrics.csv`, `table3_HR_vs_WS.csv` |
| 6 | `05_figures.py` | Figures 1, 3, 4, 5 | `05_figures/*.png`, `*.pdf` |
| 7 | `test_no_obsolete_performance_ratio.py`, `validate_results.py` | Checks | Printed to the terminal |

Warnings about transmission lines, the processed entry and expert workbooks are expected. See below.

## Validate

`run_workflow.sh` ends with `validate_results.py`. It recomputes every regional record from the equations, rebuilds the regional totals from the approved inventory and the corrections table alone, and compares outputs with `results/reference/`. It should report `0 failure(s)`. Results of the release test: `documentation/REPRODUCIBILITY_VALIDATION.md`.

## Expected results

| Quantity | Value |
|---|---:|
| Regional records | 8,516 |
| Water surface area | 27,020.03 km² |
| FPV-covered area (10%) | 2,702.00 km² |
| Installed capacity | 270.20 GW |
| Theoretical electricity | 497.07 TWh/yr |
| Theoretical evaporation reduction (upper bound) | 3.5213 km³/yr |
| Capacity factor range | 0.1392–0.2532 |
| Capacity factor median / capacity-weighted | 0.2164 / 0.2100 |
| AHP candidates | 138 |
| Robustness classes (Highly / Moderately / Partially / Weight-Sensitive) | 14 / 11 / 17 / 96 |

## What this repository does and does not reproduce

This repository **does not provide full raw-data reproducibility**. The default run starts from processed inputs.

| Reproducible here | Needs material not in this repository |
|---|---|
| Deduplication, area correction, all regional energy, capacity, CF and evaporation calculations | NID selection from the national file (optional, below) |
| Site sampling of ERA5 grids | ERA5 raw-to-grid step (optional script `00_era5_rebuild_check.py`) |
| AHP weights, scores, ranks, Monte Carlo, Tables 2 and 3 | Transmission distance regeneration (optional, below) |
| Figures 1, 3, 4, 5 | Figure 2 (state boundary layer); Figure 6 (Shiny screenshot) |
| | Real-expert scenarios (Appendix C): workbooks not distributed |
| | NHD lake attributes, CyAN HAB values, manual curation, matrix generation: upstream steps unavailable |

**Optional full regional regeneration:** place `nation.gpkg`, `US_State_Boundaries.shp` and `Electric_Power_Transmission_Lines_A.shp` (with sidecar files) in `data/regional/external/`. `run_workflow.sh` then starts from the raw NID file and regenerates transmission distances. See `documentation/DATA_SOURCES.md`.

## Known limitations

The main ones are repeated reservoir area, 18 remaining flagged areas, missing HAB data coded as "no bloom", manual curation of the AHP candidates, simulated rather than real stakeholder matrices, and evaporation that assumes 100% suppression. See `documentation/KNOWN_LIMITATIONS.md`.

## Version, citation and license

This is data version 3 (2026-11-04); see `documentation/VERSION_HISTORY.md`. Until the paper is published, cite this repository with its commit SHA. Citation details will be added on publication.

**No license has been assigned yet.** Data sources keep their own terms; see `documentation/DATA_SOURCES.md`.

The interactive Shiny application described in the paper is not in this repository.
