"""
IMOS S3 Sea Surface Temperature Query Module

Downloads the latest RAMSSA L4 analysis from the IMOS S3 bucket,
extracts SST for the Northern Beaches coastline, and falls back
to monthly climatology if real-time data is unavailable.
"""

import subprocess
import tempfile
import logging
import os
import shutil
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── S3 paths ──────────────────────────────────────────────────────────────────
RAMSSA_S3_BUCKET = "s3://imos-data"
RAMSSA_S3_PREFIX = "IMOS/SRS/SST/ghrsst/L4/RAMSSA"
NO_SIGN_REQUEST = True  # public bucket

# ── Northern Beaches bounding box ─────────────────────────────────────────────
# The coastline from Manly (-33.81°S) to Palm Beach (-33.58°S)
# We expand lon eastward to find the first ocean pixel offshore
LAT_MIN, LAT_MAX = -33.82, -33.57    # Manly → Palm Beach
LON_MIN, LON_MAX = 151.20, 152.00    # coast → ~80 km offshore

# ── Fallback monthly climatology (Sydney, °C) ─────────────────────────────────
MONTHLY_SST = {
    1: 22.0, 2: 22.5, 3: 22.0, 4: 20.5,
    5: 18.5, 6: 17.0, 7: 16.5, 8: 16.5,
    9: 17.5, 10: 18.5, 11: 20.0, 12: 21.5,
}


# ── Public helpers ─────────────────────────────────────────────────────────────

def get_water_temperature() -> dict:
    """
    Fetch real-time SST from IMOS RAMSSA L4 for the Northern Beaches coastline.

    Returns a dict:
        {"temp": float|None, "source": str, "date": str|None, "details": str}

    Falls back to monthly climatology if S3 data is unreachable or broken.
    """
    result = _fetch_ramssa_sst()
    if result is not None:
        return result

    # Fallback to monthly average
    month = datetime.now(timezone(timedelta(hours=10))).month
    temp = MONTHLY_SST[month]
    logger.info(f"Using fallback monthly SST: {temp}°C (month {month})")
    return {
        "temp": temp,
        "source": "monthly climatology",
        "date": None,
        "details": f"Monthly average for {datetime(2000, month, 1).strftime('%B')}",
    }


def get_wetsuit_recommendation(temp_celsius: float) -> str:
    """
    Recommend a wetsuit based on water temperature in °C.

    Based on standard surfing wetsuit temperature ranges:
        ≥ 22°C:  Boardshorts / rash vest
        20–21°C: Spring suit (2 mm)
        17–19°C: 3/2 steamer
        14–16°C: 4/3 steamer
        < 14°C:  5/4 steamer + boots/gloves/hood
    """
    if temp_celsius >= 22:
        return "Boardshorts or rash vest"
    elif temp_celsius >= 20:
        return "Spring suit (2 mm)"
    elif temp_celsius >= 17:
        return "3/2 steamer"
    elif temp_celsius >= 14:
        return "4/3 steamer"
    else:
        return "5/4 steamer with booties, gloves, hood"


def get_wetsuit_recommendation_by_month(month: int) -> str:
    """Legacy month-based fallback (uses climatology)."""
    return get_wetsuit_recommendation(MONTHLY_SST.get(month, 18))


# ── Internal helpers ──────────────────────────────────────────────────────────

def _find_latest_ramssa_s3_path() -> Optional[str]:
    """List the RAMSSA bucket for the current year and return the latest .nc path."""
    now = datetime.now(timezone.utc)
    year = now.year
    prefix = f"{RAMSSA_S3_PREFIX}/{year}/"

    cmd = [
        "aws", "s3", "ls",
        f"{RAMSSA_S3_BUCKET}/{prefix}",
        "--no-sign-request",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            logger.warning(f"aws s3 ls failed: {result.stderr.strip()}")
            return None

        lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
        nc_files = [l.split()[-1] for l in lines if l.endswith(".nc") and "RAMSSA" in l]
        if not nc_files:
            logger.warning("No RAMSSA .nc files found in S3 for current year")
            return None

        # Sort by filename (contains ISO-ish timestamp) to get latest
        nc_files.sort(reverse=True)
        latest = nc_files[0]
        full_path = f"{RAMSSA_S3_BUCKET}/{prefix}{latest}"
        logger.info(f"Latest RAMSSA file: {full_path}")
        return full_path

    except subprocess.TimeoutExpired:
        logger.error("S3 listing timed out")
        return None
    except Exception as e:
        logger.error(f"S3 listing failed: {e}")
        return None


def _download_ramssa_file(s3_path: str, dest: Path) -> bool:
    """Download a RAMSSA NetCDF file from S3 (public bucket)."""
    cmd = [
        "aws", "s3", "cp", s3_path, str(dest),
        "--no-sign-request",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.error(f"aws s3 cp failed: {result.stderr.strip()}")
            return False
        logger.info(f"Downloaded {s3_path} -> {dest}")
        return True
    except subprocess.TimeoutExpired:
        logger.error("S3 download timed out")
        return False
    except Exception as e:
        logger.error(f"S3 download failed: {e}")
        return False


def _parse_sst_from_netcdf(nc_path: Path) -> Optional[dict]:
    """
    Open a RAMSSA L4 NetCDF file and extract coastal SST for the
    Northern Beaches bounding box, returning the closest offshore pixel(s).
    """
    try:
        import netCDF4 as nc4
    except ImportError:
        logger.error("netCDF4 is not installed")
        return None

    try:
        ds = nc4.Dataset(str(nc_path), "r")
    except Exception as e:
        logger.error(f"Cannot open NetCDF: {e}")
        return None

    try:
        lats = ds.variables["lat"][:]
        lons = ds.variables["lon"][:]
        sst_var = ds.variables["analysed_sst"]   # auto-scaled → Kelvin
        mask_var = ds.variables["mask"]

        # Check file date
        time_val = int(ds.variables["time"][0])
        file_date = datetime(1981, 1, 1) + timedelta(seconds=time_val)

        # Compute indices for our bounding box
        lat_idx = np.where((lats >= LAT_MIN) & (lats <= LAT_MAX))[0]
        if len(lat_idx) == 0:
            logger.warning(f"No latitudes in range [{LAT_MIN}, {LAT_MAX}]")
            ds.close()
            return None

        lon_idx = np.where((lons >= LON_MIN) & (lons <= LON_MAX))[0]
        if len(lon_idx) == 0:
            logger.warning(f"No longitudes in range [{LON_MIN}, {LON_MAX}]")
            ds.close()
            return None

        # Extract the subregion
        sst_k = sst_var[0, lat_idx[0]:lat_idx[-1] + 1,
                        lon_idx[0]:lon_idx[-1] + 1]
        sst_c = sst_k - 273.15  # Kelvin → Celsius

        # Collect coastal-edge temperatures
        coastal_temps = []
        for i in range(sst_c.shape[0]):
            for j in range(sst_c.shape[1]):
                if np.ma.is_masked(sst_c[i, j]):
                    continue
                # First ocean pixel from the west
                if j == 0 or np.ma.is_masked(sst_c[i, j - 1]):
                    coastal_temps.append(float(sst_c[i, j]))

        if not coastal_temps:
            logger.warning("No ocean pixels found in the bounding box")
            ds.close()
            return None

        # Use the mean of the coastal-edge pixels as the representative SST
        avg_temp = float(np.mean(coastal_temps))
        min_temp = float(np.min(coastal_temps))
        max_temp = float(np.max(coastal_temps))
        n_pixels = len(coastal_temps)

        ds.close()

        details = (
            f"RAMSSA L4 analysis at Northern Beaches coastal edge "
            f"({n_pixels} ocean pixels; range {min_temp:.1f}–{max_temp:.1f}°C)"
        )
        logger.info(f"SST retrieved: {avg_temp:.1f}°C ({details})")

        return {
            "temp": round(avg_temp, 1),
            "source": "IMOS RAMSSA L4 satellite analysis",
            "date": file_date.strftime("%Y-%m-%d %H:%M UTC"),
            "details": details,
        }

    except Exception as e:
        logger.error(f"Error parsing NetCDF: {e}")
        ds.close()
        return None


def _fetch_ramssa_sst() -> Optional[dict]:
    """
    Full pipeline: list S3 → download latest → parse SST.
    Returns None on any failure so the caller falls back to climatology.
    """
    # Find latest file
    s3_path = _find_latest_ramssa_s3_path()
    if s3_path is None:
        return None

    # Download to a temp file
    tmp_dir = Path(tempfile.mkdtemp(prefix="imos_sst_"))
    nc_path = tmp_dir / "ramssa_latest.nc"
    try:
        if not _download_ramssa_file(s3_path, nc_path):
            return None

        # Parse
        result = _parse_sst_from_netcdf(nc_path)
        return result

    finally:
        # Clean up temp directory
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ── CLI test ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    result = get_water_temperature()
    print(f"\nWater temperature: {result['temp']}°C")
    print(f"Source: {result['source']}")
    print(f"Date: {result['date']}")
    print(f"Details: {result['details']}")
    print(f"Wetsuit: {get_wetsuit_recommendation(result['temp'])}")
