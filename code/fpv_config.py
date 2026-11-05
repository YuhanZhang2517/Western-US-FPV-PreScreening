"""Paths and documented parameters for the four-script FPV workflow.

Every path is resolved relative to the repository root, one level above this file.

Every scientific parameter carries the source it was copied from. None was tuned.
"""
from pathlib import Path

# --------------------------------------------------------------------------- paths
HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parent                                # repository root
DATA = WORKSPACE / "data"
REGIONAL = DATA / "regional"
AHP = DATA / "ahp"
OUTPUT_ROOT = WORKSPACE / "outputs"                    # created by the workflow; not tracked by Git
RUN_ID = "run"
STAGE_DIRS = {0: "00_era5_check", 1: "01_data_preparation", "1b": "01b_deduplication", 2: "02_data_processing",
              3: "03_AHP_analysis", 4: "04_sensitivity_analysis", 5: "05_figures"}
EXPECTED_REGIONAL_RECORDS = 8516                       # integrity check on the approved inventory

# --------------------------------------------------------------------------- Pathway A inputs
NID_GPKG = REGIONAL / "nid_identifiers_west.sqlite"    # identifiers only; see documentation/DATA_SOURCES.md
NID_FULL_GPKG = REGIONAL / "external" / "nation.gpkg"  # optional raw NID; not distributed
NID_LAYER = "dams"
STATE_SHP = REGIONAL / "external" / "US_State_Boundaries.shp"                       # optional; not distributed
TRANSMISSION_SHP = REGIONAL / "external" / "Electric_Power_Transmission_Lines_A.shp"  # optional; not distributed
ERA5_GRIDS = {  # output column: (file, layer, value column)
    "solar_Jm2": (REGIONAL / "era5_grids" / "avg_annual_solar_2020_2024.gpkg", None, "avg_annual_solar_J/m2"),
    "evap_m_per_yr": (REGIONAL / "era5_grids" / "avg_annual_evaporation_2020_2024.gpkg", None, "avg_annual_evap_m"),
    "ice_m": (REGIONAL / "era5_grids" / "max_ice.gpkg", "max_ice_points", "max_ice"),
    "wind_ms": (REGIONAL / "era5_grids" / "max_wind.gpkg", "max_wind_points", "max_wind"),
}
NATURAL_LAKE_SOURCE_DIR = REGIONAL / "natural_lake_source"
PROCESSED_ENTRY_8507 = REGIONAL / "historical_inputs" / "nid_selected.csv"
INVENTORY_8520_CSV = REGIONAL / "historical_inputs" / "nid_selected_with_natural_lakes.csv"
APPROVED_DIR = REGIONAL / "review"
AREA_REVIEW_FLAGS = REGIONAL / "review" / "area_review_flags_19.csv"
AREA_CORRECTIONS = REGIONAL / "corrections" / "surface_area_corrections.csv"   # author-approved, applied in 01b

# --------------------------------------------------------------------------- Pathway B inputs
CURATED_DIR = AHP / "curated_top30"
CURATED_FILES = ["Federal_Top30_Solar_cleaned.csv", "LocalGov_Top30_Solar_cleaned.csv",
                 "Private_Top30_Solar_cleaned.csv", "State_Top30_Solar_cleaned.csv",
                 "Utility_Top30_Solar_cleaned.csv"]
SIMULATED_MATRICES_XLSX = AHP / "matrices" / "AHP_Saaty_random_experts_alpha10_byStakeholder.xlsx"
AGGREGATED_MATRIX_XLSX = AHP / "matrices" / "CF438420.xlsx"
# Real-expert workbooks are not distributed. Place them here, if you hold them, to run the expert scenarios.
EXPERT_RAW = {"Expert_1": AHP / "experts" / "Expert_1.xlsx", "Expert_2": AHP / "experts" / "Expert_2.xlsx"}

# --------------------------------------------------------------------------- Script 1 parameters
WESTERN_STATES = ["California", "Oregon", "Washington", "Nevada", "Utah", "Arizona",
                  "New Mexico", "Colorado", "Idaho", "Montana", "Wyoming"]   # NID_process.ipynb cell 9
NID_COLUMNS = ["name", "nidId", "federalId", "state", "ownerTypeIds", "primaryOwnerTypeId", "purposeIds",
               "surfaceArea", "geometry", "latitude", "longitude"]           # cell 9 (+ nidId/federalId for tracing)
ACRE_TO_SQKM = 0.00404685642          # NID_process.ipynb; merge_natural_lakes_into_nid.py
# merge_natural_lakes_into_nid.py: CONFIRMED_NATURAL (13), EXCLUDED_POSSIBLE (8), TOP30_FILE_ORDER
CONFIRMED_NATURAL = ["Salton Sea", "Great Salt Lake", "Goose Lake", "Yellowstone Lake", "Bear Lake",
                     "Honey Lake", "Mono Lake", "Lake Abert", "Summer Lake", "Walker Lake", "Malheur Lake",
                     "Lake Washington", "Lake Elsinore"]
EXCLUDED_POSSIBLE = {
    "Washoe Lake": "name-identical NID dam 'Washoe Lake Dam' (NV) 5.5 km away; not workflow-linked",
    "Heron Reservoir": "name-identical NID dam 'Heron Dam' (NM) 3.4 km away; not workflow-linked",
    "Willard Bay Reservoir": "impounded by NID 'Arthur V. Watkins Dam' (UT) 2.9 km away",
    "Lake Pleasant": "impounded by NID 'New Waddell Dam' (AZ) 7.1 km away",
    "Franklin D Roosevelt Lake": "IS the Grand Coulee Dam reservoir; NID 'Grand Coulee Dam' present ~78 km upstream-end",
    "Coeur d'Alene Lake": "level-regulated by NID 'Post Falls * Channel' (ID) ~21.6 km away",
    "Utah Lake": "NID 'Utah Lake Outlet' present in the 12,349-row file (dropped by surfaceArea>0 filter)",
    "Riffe Lake": "reservoir of Mossyrock Dam; Mossyrock Dam absent from nid_selected.csv",
}
TOP30_FILE_ORDER_FOR_LAKES = ["Federal_Top30_Solar_cleaned.csv", "State_Top30_Solar_cleaned.csv",
                              "LocalGov_Top30_Solar_cleaned.csv", "Utility_Top30_Solar_cleaned.csv",
                              "Private_Top30_Solar_cleaned.csv"]
DUP_DIST_M, AMBIG_DIST_M = 500.0, 2000.0              # merge script de-duplication tolerances
FIG1_ACRE_TO_M2 = 4046.856                            # AHP notebook cell 1 (Figure 1 statistics)
FIG1_THRESHOLD_M2 = 10e6                              # AHP notebook cell 1: "reservoirs > 10 km2"

# --------------------------------------------------------------------------- Script 2 parameters
J_PER_KWH = 3_600_000.0               # NID_process.ipynb cell 23
PROJECTED_CRS = "EPSG:5070"           # NID_process.ipynb cell 19 (distance to transmission)
F_COV = 0.10                          # manuscript Sec. 2.3.1 Eq. 1; Excel col P (=0.1*O*I)
ETA = 0.10                            # manuscript Sec. 2.3.1 Eq. 4; applied by hand (author, M3/M4)
POWER_DENSITY_MW_PER_KM2 = 100.0      # D_p, manuscript Sec. 2.3.1 lines 185-186
STC_IRRADIANCE_KW_PER_M2 = 1.0        # reference irradiance, manuscript Sec. 2.3.1 line 189
assert abs(ETA - POWER_DENSITY_MW_PER_KM2 * 1e-3 / STC_IRRADIANCE_KW_PER_M2) < 1e-12   # eta = D_p / STC
ACRE_TO_M2_EXCEL = 4046.86            # Excel col O (author-confirmed stage 1, M4)
ACRE_TO_M2_MERGE = 4046.856           # merge_natural_lakes_into_nid.py sec. 9 (sensitivity column only)
EVAP_SUPPRESSION_FRACTION = 1.0       # IMPLICIT in Excel col Q (=0.1*A*PEV): no suppression factor (M5).
#                                       Labelled THEORETICAL UPPER BOUND in every output. Not a chosen value.
HOURS_PER_YEAR = 8760                 # Eq. 3 denominator. CF = G / 8760; no performance ratio (see fpv_calculations.py)
ICE_THRESHOLD_M = 0.0                 # Ice_binary = (max ice depth > 0), Rankplot.ipynb cell 31

# --------------------------------------------------------------------------- Script 3 parameters (notebook cell 2)
VARIABLES = ["Annual_evaporation", "Ice_binary", "max_wind_ms", "nearest_dist_m", "log_Annual_solar_GWh",
             "Capacity_Factor", "HAB_flag_20k", "Ownership_Score", "State_Score"]
HIGHER_IS_BETTER = {"Annual_evaporation": True, "Ice_binary": False, "max_wind_ms": False,
                    "nearest_dist_m": False, "log_Annual_solar_GWh": True, "Capacity_Factor": True,
                    "HAB_flag_20k": True, "Ownership_Score": False, "State_Score": False}
IS_BINARY = {"Annual_evaporation": False, "Ice_binary": True, "max_wind_ms": False, "nearest_dist_m": False,
             "log_Annual_solar_GWh": False, "Capacity_Factor": False, "HAB_flag_20k": True,
             "Ownership_Score": False, "State_Score": False}
# notebook cell 9 criterion_mapping (Excel label -> variable)
CRITERION_MAPPING = {"Solar Radiation": "log_Annual_solar_GWh", "Water body Evaporation": "Annual_evaporation",
                     "Ice Issue": "Ice_binary", "Wind Load": "max_wind_ms",
                     "Distance to Transmission Line": "nearest_dist_m", "Solar Capacity": "Capacity_Factor",
                     "Algae Issue": "HAB_flag_20k", "Water Body Ownership": "Ownership_Score",
                     "State": "State_Score"}
EXCEL_CRITERIA_ORDER = ["Ice Issue", "Algae Issue", "Wind Load", "Solar Radiation",
                        "Distance to Transmission Line", "Water body Evaporation", "Solar Capacity",
                        "Water Body Ownership", "State"]
# notebook cell 9 RI_values
RANDOM_INDEX = {1: 0.00, 2: 0.00, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49,
                11: 1.51, 12: 1.48, 13: 1.56, 14: 1.57, 15: 1.59}
CR_THRESHOLD = 0.10                   # manuscript Sec. 2.4 (reported only; never used to exclude a matrix)
# notebook cell 7 assign_state_regulation_score (author's own docstring: "placeholder values")
STATE_SCORES = {"ARIZONA": 4, "CALIFORNIA": 10, "COLORADO": 6, "IDAHO": 3, "MONTANA": 6, "NEVADA": 5,
                "NEW MEXICO": 4, "OREGON": 7, "UTAH": 4, "WASHINGTON": 8, "WYOMING": 5}
STATE_SCORE_DEFAULT = 5
TOP_N = 30

# --------------------------------------------------------------------------- Script 4 parameters (notebook cell 18)
N_SIMULATIONS = 10000
PERTURBATION_FACTOR = 0.5
RANDOM_SEED = 42                      # np.random.seed(42), legacy MT19937 stream
WEIGHT_FLOOR = 0.01                   # max(0.01, perturbed) before renormalisation
# robustness classes (cell 18): evaluated in this order
ROBUSTNESS_RULES = [("Highly Robust", 0.8, 10), ("Moderately Robust", 0.5, 20), ("Partially Robust", 0.2, None)]
ROBUSTNESS_DEFAULT = "Weight-Sensitive"
