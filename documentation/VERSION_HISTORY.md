# Data correction and version history

| Version | Date | Records | Change | Water area (km²) | Capacity (GW) | Electricity (TWh/yr) | Evaporation (km³/yr) |
|---|---|---:|---|---:|---:|---:|---:|
| 1 | 2026-10-30 | 8,520 | Reconstructed historical inventory | 28,577.14 | 285.77 | 526.64 | 3.7132 |
| 2 | 2026-11-03 | 8,516 | Duplicate review removed 4 records; 3 manual keeps. Abandoned 0.8 factor removed from capacity factor | 28,563.72 | 285.64 | 526.37 | 3.7117 |
| **3** | **2026-11-04** | **8,516** | **Flatiron Dam area corrected** | **27,020.03** | **270.20** | **497.07** | **3.5213** |

## Version 3: Flatiron Dam

| | Source (NID) | Corrected |
|---|---:|---:|
| Surface area (acres) | 381,500 | 45 |
| Surface area (km²) | 1,543.88 | 0.182 |
| Installed capacity (MW) | 15,438.8 | 1.82 |
| Electricity (MWh/yr) | 29,299,822 | 3,456 |
| Evaporation reduction (m³/yr) | 190,396,712 | 22,458 |

- **Record:** NID ID CO01654, `record_id` 681, Colorado.
- **Approval:** the authors set 45 acres on 2026-11-04. Evidence is in `DATA_SOURCES.md`.
- **Files that keep the source value on purpose:** `data/regional/historical_inputs/`, `data/regional/review/`, and the March 2026 files directly under `data/`. The workflow corrects it in `01b_deduplication.py`.
- **Effects:** only this record's area-dependent values, the Colorado and regional totals, and the Figure 1 statistics changed (339 records above 10 km², 3.98% of records, 85.3% of area; previously 340, 3.99%, 86.1%). Area review flags fall from 19 to 18.
- **Unchanged:** capacity factor of this record (it depends on irradiation, not area), and every AHP, Monte Carlo and statistical result. Flatiron is not one of the 138 candidates.

The manuscript draft may still show version 1 or 2 regional values until it is updated.
