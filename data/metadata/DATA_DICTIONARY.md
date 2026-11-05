# Data dictionary

## `data/regional/regional_fpv_inventory_8516.csv`

| Column | Unit | Meaning |
|---|---|---|
| `record_id` | | Row in the 8,520-record input |
| `source_id`, `source_id_status` | | NID Dam ID, and whether it is valid, ambiguous or absent |
| `name`, `state`, `latitude`, `longitude` | degrees | Identity and location |
| `ownerTypeIds`, `primaryOwnerTypeId`, `purposeIds` | | NID categories |
| `surfaceArea` | acres | Surface area used: NID or NHD value, or the approved correction |
| `surfaceArea_source_acres` | acres | Area before correction |
| `area_correction_applied` | | True for corrected records (Flatiron Dam) |
| `surfaceArea_sqkm` | km² | Area using 0.00404685642 km²/acre |
| `solar_Jm2` | J m⁻² yr⁻¹ | ERA5 solar; blank for the 13 lakes |
| `solar_kWhm2` | kWh m⁻² yr⁻¹ | G |
| `evap_m_per_yr` | m/yr | ERA5 potential evaporation |
| `ice_m`, `wind_ms` | m; m/s | Maximum lake ice depth; maximum 10 m wind |
| `dist_to_grid_m` | m | Distance to nearest transmission line |
| `Capacity_Factor` | none | Eq. 3 |
| `max_HAB_2020_2024`, `HAB_flag_20k` | cells/mL; flag | CyAN values, for lakes where available |
| `source_dataset`, `is_natural_water_body` | | NID or NHD |
| `surface_area_km2` | km² | Area used in calculations (4046.86 m²/acre) |
| `fpv_area_km2` | km² | Eq. 1 |
| `installed_capacity_MW` | MW | D_p × A_FPV |
| `incident_solar_kWh_per_yr` | kWh/yr | Eq. 2 |
| `annual_electricity_MWh` | MWh/yr | Eq. 4 |
| `evap_reduction_upper_bound_m3_per_yr` | m³/yr | Theoretical maximum |
| `cf_status`, `cf_missing_reason` | | Calculation status |
| `area_review_flag` | | True for the 18 flagged records still at their source area |

## `data/ahp/ahp_candidates_138.csv`

Curated attributes plus: `Source_File`, `State_Score`, `Ownership_Score`, `OwnershipType`, one `<criterion>_category` (1–10) per criterion, `AHP_Score`, `Rank`. `Capacity_Factor` here is the recalculated Eq. 3 value.

## Criteria

`Annual_evaporation`, `Ice_binary`, `max_wind_ms`, `nearest_dist_m`, `log_Annual_solar_GWh`, `Capacity_Factor`, `HAB_flag_20k`, `Ownership_Score`, `State_Score`.
