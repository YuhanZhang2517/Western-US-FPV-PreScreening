# Methodology

## Regional calculations (manuscript Sec 2.3.1, Eq. 1–4)

Implemented in `code/fpv_calculations.py`.

| Step | Formula | Units |
|---|---|---|
| Eq. 1 | A_FPV = 0.10 × A | km² |
| Eq. 2 | E_solar = G × A_FPV | kWh/yr |
| Eq. 4 | E_annual = 0.10 × E_solar | MWh/yr after conversion |
| Text | P_installed = 100 MW km⁻² × A_FPV | MW |
| Eq. 3 | CF = E_annual / (P_installed × 8760) | dimensionless |
| Evaporation | V = 0.10 × A × PEV | m³/yr |

- **Area:** NID area in acres × 4046.86 m²/acre. Figure 1 statistics use 4046.856, as in the original figure code.
- **G:** mean annual ERA5 SSRD, 2020–2024, kWh m⁻² yr⁻¹.
- **η = 0.10:** 100 MW km⁻² relative to 1 kW m⁻². It is an area-based conversion factor.
- **No performance ratio or loss factor** is applied. A former 0.8 factor was abandoned. It survives only as a stored column in some input files, which the code does not use.
- **Installed capacity** is in MW as stated in the manuscript. DC or AC is not specified.
- **Evaporation** assumes all potential evaporation under the covered area is avoided. It is a theoretical upper bound, not realistic net water savings.

## Deduplication

`reservoir_duplicate_review.py` groups records by normalized name, state and exact area. It uses no fuzzy or geographic matching, and it does not merge records because they share a Dam ID. `MANUAL_KEEP` retains three verified distinct reservoirs.

## Surface-area correction

`01b_deduplication.py` first confirms that the duplicate review reproduces the approved inventory byte for byte. It then applies `data/regional/corrections/surface_area_corrections.csv`, stopping unless each entry matches exactly one record at its documented source value. Only `surfaceArea` and `surfaceArea_sqkm` change. One correction exists: Flatiron Dam (CO01654), 381,500 → 45 acres. All later steps use the corrected inventory. The correction does not touch the AHP pathway because Flatiron is not one of the 138 candidates.

## AHP

1. Load five curated files (149 rows) and merge by name and state to 138 sites.
2. Recalculate capacity factor from Eq. 1–4.
3. Score nine criteria from 1 (best) to 10 (worst) using deciles. Binary criteria take 1 or 10.
4. Aggregate all 100 matrices by geometric mean. Derive weights from the principal eigenvector, with RI = 1.45.
5. Composite score = Σ weight × score. Lower is better. Ties use `rank(method="min")`; none occur.

**Bin rule:** when ties collapse decile bins, scores are rescaled as `1 + bin × 9/(bins−1)` and rounded with pandas `.round()` (half to even). This affects distance, ownership and State, and it is not described in the manuscript. See `KNOWN_LIMITATIONS.md`.

## Monte Carlo

10,000 simulations, seed 42, each weight multiplied by 1 + U(−0.5, 0.5), floor 0.01, renormalized.

| Class | Rule |
|---|---|
| Highly Robust | P(Top-30) ≥ 0.8 and rank IQR ≤ 10 |
| Moderately Robust | P ≥ 0.5 and rank IQR ≤ 20 |
| Partially Robust | P ≥ 0.2 |
| Weight-Sensitive | Otherwise (P < 0.2) |

Table 3 uses a two-sided Mann-Whitney U test with r = 1 − 2U/(n₁n₂).
