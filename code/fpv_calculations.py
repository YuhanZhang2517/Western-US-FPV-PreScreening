"""FPV energy, installed capacity and capacity factor: manuscript Sec 2.3.1, Eq. 1-4 (pp. 9-10).

  Eq. 1   A_FPV       = f_cov * A
  Eq. 2   E_solar     = G * A_FPV
  Eq. 4   E_annual    = eta * E_solar
  text    P_installed = D_p * A_FPV                (lines 185-186; no equation number)
  Eq. 3   CF          = E_annual / (P_installed * 8760)

Units: A, A_FPV km2; G kWh m-2 yr-1; E_solar kWh yr-1; E_annual MWh yr-1; P_installed MW; CF dimensionless.
With eta = 0.10 and D_p = 100 MW km-2, area cancels and CF = G / 8760.

No performance ratio, temperature or system-loss factor is applied. The former 0.8 performance ratio is
abandoned (author decision, 2026-11-03) and must not be reintroduced. P_installed is in MW exactly as the
manuscript states it; the manuscript does not say whether this is DC or AC.
"""
import numpy as np
import pandas as pd

import fpv_config as C

M2_PER_KM2 = 1e6
KWH_PER_MWH = 1e3


def fpv_metrics(area_km2, solar_kwh_m2):
    """Return site-level quantities. Records with invalid inputs stay in the table with NaN and a reason."""
    area = pd.to_numeric(pd.Series(area_km2), errors="coerce")
    solar = pd.to_numeric(pd.Series(solar_kwh_m2), errors="coerce").set_axis(area.index)
    area_ok = np.isfinite(area) & (area > 0)
    solar_ok = np.isfinite(solar) & (solar > 0)
    ok = area_ok & solar_ok
    fpv_area_km2 = C.F_COV * area                                            # Eq. 1
    incident_kwh = solar * fpv_area_km2 * M2_PER_KM2                         # Eq. 2
    electricity_mwh = C.ETA * incident_kwh / KWH_PER_MWH                     # Eq. 4
    installed_mw = C.POWER_DENSITY_MW_PER_KM2 * fpv_area_km2                 # text, lines 185-186
    capacity_factor = (electricity_mwh / (installed_mw * C.HOURS_PER_YEAR)).where(ok)   # Eq. 3
    reason = np.select([~area_ok & ~solar_ok, ~area_ok, ~solar_ok],
                       ["surface area and solar input invalid", "surface area invalid", "solar input invalid"], "")
    return pd.DataFrame({"fpv_area_km2": fpv_area_km2, "incident_solar_kWh_per_yr": incident_kwh,
                         "annual_electricity_MWh": electricity_mwh, "installed_capacity_MW": installed_mw,
                         "Capacity_Factor": capacity_factor, "cf_status": np.where(ok, "calculated", "not calculated"),
                         "cf_missing_reason": reason}, index=area.index)


def assert_cf_follows_eq3(capacity_factor, solar_kwh_m2):
    """Stop before any result is written if CF is not G/8760, which would reveal a hidden factor such as 0.8."""
    ratio = np.asarray(capacity_factor, dtype=float) / (np.asarray(solar_kwh_m2, dtype=float) / C.HOURS_PER_YEAR)
    ratio = ratio[np.isfinite(ratio)]
    if ratio.size == 0 or np.abs(ratio - 1).max() > 1e-12:
        raise RuntimeError("Capacity_Factor does not equal G/8760; an unapproved factor may be active")
    return float(np.abs(ratio - 1).max())


def capacity_weighted_cf(electricity_mwh, installed_mw):
    """Sum of generation over sum of (capacity x hours). Regional statistic; the manuscript defines none."""
    return float(np.nansum(electricity_mwh) / (np.nansum(installed_mw) * C.HOURS_PER_YEAR))
