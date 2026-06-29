#!/usr/bin/env python3
"""
Surforecast - Automated Surf Report Generator for GitHub Pages

Generates a daily surf report for NSW beaches and publishes it as a static HTML page
to trigger GitHub Pages deployment.
"""

import requests
import json
import datetime
import math
import os
import sys
import logging
from pathlib import Path

import imos_sst
import llm_report

# Configuration
LOCATION = {"latitude": -33.78, "longitude": 151.30}  # Sydney
REPORT_TIME_HOUR = 6  # 6:00 AM report time (kept for reference)

# Timeframes shown on the page — midpoint hour used for data lookup
TIMEFRAMES = [
    {"label": "6–9am",   "hour": 7,  "emoji": "🌅"},
    {"label": "9–12pm",  "hour": 10, "emoji": "☀️"},
    {"label": "12–3pm",  "hour": 13, "emoji": "🌤️"},
    {"label": "3–6pm",   "hour": 16, "emoji": "🌇"},
]

BEACHES = {
    "Long Reef":     {"aspect": 158, "left_offset": 68, "right_offset": 22},
    "Dee Why":       {"aspect": 135, "left_offset": 67.5, "right_offset": 22.5},
    "Curl Curl":     {"aspect": 112, "left_offset": 44.5, "right_offset": 45.5},
    "Freshwater":    {"aspect": 135, "left_offset": 35, "right_offset": 22.5},
    "North Steyne":  {"aspect": 90,  "left_offset": 45, "right_offset": 45},
    "South Steyne":  {"aspect": 68,  "left_offset": 45.5, "right_offset": 22},
}
BEACH_NOTES = {
    "Long Reef": "Northernmost beach, southeast-southeast exposure",
    "Dee Why": "Southeast facing beach, sheltered by southern headland",
    "Curl Curl": "East-southeast exposed beach with consistent swell",
    "Freshwater": "Southeast facing beach, protected by northern headland",
    "North Steyne": "Eastern end of Manly Beach, exposed to east swells",
    "South Steyne": "East-northeast end of Manly Beach, NE swell exposure"
}


def load_beaches_config(config_path="beaches.json"):
    """Load beach configuration from a JSON file, falling back to hardcoded defaults."""
    global BEACHES, BEACH_NOTES
    try:
        with open(config_path, 'r') as f:
            data = json.load(f)
        loaded = {}
        notes = {}
        for b in data.get("beaches", []):
            name = b["name"]
            loaded[name] = {
                "aspect": b["primary_aspect"],
                "left_offset": b.get("left_offset", 10),
                "right_offset": b.get("right_offset", 10),
            }
            notes[name] = b.get("notes", "")
        if loaded:
            BEACHES = loaded
            BEACH_NOTES = notes
            logger.info(f"Loaded {len(loaded)} beaches from {config_path}")
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Could not load {config_path}: {e}. Using hardcoded defaults.")

LOG_FILE = Path.home() / "surforecast.log"
REPORT_FILE = Path("docs") / "index.html"  # GitHub Pages serves from /docs
ERROR_REPORT_FILE = Path("docs") / "error.html"

# Fallback wetsuit guide by month (used only when real SST is unavailable)
FALLBACK_WETSUIT_GUIDE = {
    12: "Boardshorts or rash vest",
    1: "Boardshorts or rash vest", 
    2: "Boardshorts or rash vest",
    3: "Spring suit (2mm)",
    4: "Spring suit (2mm)",
    5: "3/2 steamer",
    6: "4/3 steamer",
    7: "4/3 steamer",
    8: "4/3 steamer",
    9: "3/2 steamer",
    10: "3/2 steamer",
    11: "Spring suit (2mm)",
    12: "Boardshorts or rash vest"
}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Load beach config from JSON file (falls back to hardcoded defaults)
load_beaches_config()


def fetch_marine_forecast():
    """Fetch marine forecast data from Open-Meteo API."""
    url = "https://marine-api.open-meteo.com/v1/marine"
    params = {
        "latitude": LOCATION["latitude"],
        "longitude": LOCATION["longitude"],
        "hourly": "wave_height,wave_period,wave_direction",
        "timezone": "Australia/Sydney"
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        logger.info("Successfully fetched marine forecast")
        return data
    except Exception as e:
        logger.error(f"Failed to fetch marine forecast: {e}")
        return None


def fetch_wind_forecast():
    """Fetch wind forecast data from Open-Meteo API."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LOCATION["latitude"],
        "longitude": LOCATION["longitude"],
        "hourly": "windspeed,winddirection",
        "timezone": "Australia/Sydney"
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        logger.info("Successfully fetched wind forecast")
        return data
    except Exception as e:
        logger.error(f"Failed to fetch wind forecast: {e}")
        return None


def fetch_current_tide_from_mhl():
    """Fetch current tide observation from MHL Station 213470 (optional, falls back to harmonic model)."""
    # MHL API is currently unavailable; we use the harmonic tide model instead
    return None


def harmonic_tide(dt, msl=0.9, m2_amp=0.57, s2_amp=0.16):
    """
    Harmonic tide model for Sydney (M2 + S2 constituents).
    Uses epoch-based calculation for continuous prediction across days.
    Returns tide height in metres above Chart Datum.
    
    Sydney (Port Jackson / Fort Denison) parameters:
    - MSL: ~0.9m above Chart Datum
    - M2 (principal lunar): amplitude 0.57m, period 12.42h
    - S2 (principal solar): amplitude 0.16m, period 12.00h
    """
    # Use Jan 1, 2000 as epoch for continuous phase calculation
    epoch = datetime.datetime(2000, 1, 1, tzinfo=dt.tzinfo)
    hours_since_epoch = (dt - epoch).total_seconds() / 3600.0
    
    # M2 constituent (lunar semi-diurnal, period ~12.42h)
    # Phase shifts 50 mins later each day, epoch-based calc handles this
    m2_period = 12.42
    m2_phase = 6.56  # hours, calibrated for Sydney
    m2 = m2_amp * math.sin(2 * math.pi * (hours_since_epoch / m2_period - m2_phase / 24))
    
    # S2 constituent (solar semi-diurnal, period exactly 12h)
    s2_period = 12.00
    s2_phase = 7.5  # hours, calibrated for Sydney
    s2 = s2_amp * math.sin(2 * math.pi * (hours_since_epoch / s2_period - s2_phase / 24))
    
    return msl + m2 + s2


def tide_lookup(target_dt, obs_data=None):
    """
    Get tide height for target datetime, using observed data if available
    and anchored harmonic model, otherwise pure harmonic model.
    """
    if obs_data:
        obs_height = obs_data["height"]
        obs_dt = obs_data["timestamp"]
        
        # Use observation to anchor the harmonic model
        # Calculate what the harmonic model predicts at observation time
        predicted_at_obs = harmonic_tide(obs_dt)
        # Calculate offset to make model match observation
        msl_offset = obs_height - predicted_at_obs
        
        # Return adjusted harmonic prediction for target time
        return harmonic_tide(target_dt, msl=msl_offset) + msl_offset
    else:
        # Fallback to pure harmonic model
        return harmonic_tide(target_dt)


def get_tide_trend(current_height, past_height, future_height):
    """Determine tide trend based on height changes."""
    if future_height > current_height > past_height:
        return "rising"
    elif future_height < current_height < past_height:
        return "falling"
    elif abs(future_height - current_height) < 0.05 and abs(current_height - past_height) < 0.05:
        return "slack"
    elif current_height >= past_height and current_height >= future_height:
        return "high"
    elif current_height <= past_height and current_height <= future_height:
        return "low"
    else:
        return "changing"


def _diffraction_coefficient(shadow_angle):
    """
    Diffraction coefficient Kd from Wiegel's curves for a beach 5–10 wavelengths
    from the headland tip.  Maps shadow angle (degrees past the direct window edge)
    to the fraction of offshore wave height that reaches the beach.
    """
    if shadow_angle <= 0:
        return 1.0  # inside the direct window, no diffraction loss

    # Midpoints from the Wiegel curve table
    curve = [
        (0,   0.70),
        (10,  0.55),
        (30,  0.40),
        (60,  0.225),
        (90,  0.15),
    ]

    for i in range(len(curve) - 1):
        x1, y1 = curve[i]
        x2, y2 = curve[i + 1]
        if x1 <= shadow_angle <= x2:
            t = (shadow_angle - x1) / (x2 - x1)
            return y1 + t * (y2 - y1)

    # Extrapolate beyond 90° using the slope from the last two points, floor at 0
    x1, y1 = curve[-2]
    x2, y2 = curve[-1]
    slope = (y2 - y1) / (x2 - x1)
    result = y2 + slope * (shadow_angle - x2)
    return max(0.0, result)


def _angle_of_attack_factor(attack_angle):
    """
    Rideability factor based on the angle between swell direction and beach aspect.

    For straight beach breaks (not points or reefs), the angle of attack determines
    whether waves close out, peel perfectly, or arrive weak after excessive refraction.

    Zones based on surf science literature:
      0°–10°  (close-out)     → poor, wave shuts down all at once
     15°–45°  (perfect peeler) → excellent, peeling down the line
     60°+     (extreme angle)  → weak, wave loses energy refracting
    """
    curve = [
        (0,   0.5),   # straight-on close-out — half penalty
        (10,  0.6),   # edge of close-out zone
        (15,  1.0),   # peeler zone begins — no penalty
        (45,  1.0),   # peeler zone ends — no penalty
        (60,  0.65),  # extreme angle begins
        (90,  0.5),   # extreme — half penalty
    ]

    if attack_angle < 0:
        return 1.0

    for i in range(len(curve) - 1):
        x1, y1 = curve[i]
        x2, y2 = curve[i + 1]
        if x1 <= attack_angle <= x2:
            t = (attack_angle - x1) / (x2 - x1)
            return y1 + t * (y2 - y1)

    # Beyond 90° — extrapolate down
    return max(0.0, 0.3 - (attack_angle - 90) * 0.01)


def sunrise_sunset(date, lat=-33.78, lon=151.30, tz=10):
    """
    Calculate sunrise and sunset times for Northern Beaches area.
    Returns (sunrise_local, sunset_local) as decimal hours in AEST.
    Uses NOAA solar position algorithm.
    """
    doy = date.timetuple().tm_yday

    # Solar declination (degrees)
    decl = 23.45 * math.sin(math.radians(360.0 / 365 * (doy - 81)))

    # Cosine of hour angle
    cos_ha = -math.tan(math.radians(lat)) * math.tan(math.radians(decl))
    cos_ha = max(-1.0, min(1.0, cos_ha))
    ha = math.degrees(math.acos(cos_ha))

    # Equation of time (minutes)
    B = 360.0 / 365 * (doy - 81)
    eot = (9.87 * math.sin(math.radians(2 * B))
           - 7.53 * math.cos(math.radians(B))
           - 1.5 * math.sin(math.radians(B)))

    # Sunrise/sunset in local time (AEST = UTC+10)
    # Formula: local = 12 - (lon +/- ha)/15 - eot/60 + tz
    sunrise_local = 12 - (lon + ha) / 15 - eot / 60 + tz
    sunset_local  = 12 - (lon - ha) / 15 - eot / 60 + tz

    return (sunrise_local % 24, sunset_local % 24)


def solar_elevation_azimuth(hour, date, lat=-33.78, lon=151.30):
    """
    Compute solar elevation (degrees above horizon) and azimuth (degrees from north)
    for a given hour (local AEST) and date at the Northern Beaches.
    Returns (elevation, azimuth_compass).
    """
    doy = date.timetuple().tm_yday

    # Solar declination (degrees)
    decl = 23.45 * math.sin(math.radians(360.0 / 365 * (doy - 81)))

    # Equation of time (minutes)
    B = 360.0 / 365 * (doy - 81)
    eot = (9.87 * math.sin(math.radians(2 * B))
           - 7.53 * math.cos(math.radians(B))
           - 1.5 * math.sin(math.radians(B)))

    # Convert local time to UTC, then to hour angle
    utc_hour = hour - 10  # AEST = UTC+10
    # Hour angle (degrees): 15° per hour from solar noon
    ha_deg = 15 * (utc_hour + (lon / 15) - 12 + eot / 60)

    # Solar elevation (degrees above horizon)
    sin_alt = (math.sin(math.radians(lat)) * math.sin(math.radians(decl))
               + math.cos(math.radians(lat)) * math.cos(math.radians(decl))
               * math.cos(math.radians(ha_deg)))
    sin_alt = max(-1.0, min(1.0, sin_alt))
    elevation = math.degrees(math.asin(sin_alt))

    # Solar azimuth (degrees from north, clockwise)
    cos_az = ((math.sin(math.radians(decl)) - math.sin(math.radians(lat)) * sin_alt)
              / (math.cos(math.radians(lat)) * math.cos(math.radians(elevation))))
    cos_az = max(-1.0, min(1.0, cos_az))
    # Determine correct quadrant
    if ha_deg > 0:
        # After noon (afternoon) - sun is in the west
        azimuth = 360 - math.degrees(math.acos(cos_az))
    else:
        # Before noon (morning) - sun is in the east
        azimuth = math.degrees(math.acos(cos_az))

    return (elevation, azimuth)


def uv_index(solar_elevation):
    """Estimate UV index from solar elevation (degrees above horizon)."""
    if solar_elevation <= 0:
        return 0  # Night
    elif solar_elevation < 15:
        return min(2, int(solar_elevation / 7.5))  # 0-2, Low
    elif solar_elevation < 30:
        return 3 + int((solar_elevation - 15) / 5)  # 3-5, Moderate
    elif solar_elevation < 45:
        return 6 + int((solar_elevation - 30) / 5)  # 6-8, High
    elif solar_elevation < 60:
        return 9 + int((solar_elevation - 45) / 5)  # 9-10, Very High
    else:
        return 11  # Extreme


def hat_recommendation(uv, sun_compass, beach_names, timeframes_conditions):
    """
    Recommend hat type based on UV index and sun exposure.
    Returns (hat_type, uv_label).
    """
    if uv <= 0:
        return ("Not needed", "None")
    if uv <= 2:
        return ("Cap", "Low")
    elif uv <= 5:
        return ("Bucket hat", "Moderate")
    else:
        return ("Legionnaire's cap", "High")

def shoal_factor(period):
    """
    Amplification from shoaling for a wave of given period (seconds).
    Longer-period waves carry more energy and amplify more as they rise before breaking.
    6s windswell ≈ no amplification.  18s+ groundswell ≈ 1.6× amplification.
    """
    if period < 6:
        return 1.0
    elif period >= 18:
        return 1.6
    else:
        return 1.0 + (period - 6) * 0.6 / 12


def embayment_factor(left_offset, right_offset, effective_height, wave_period):
    """
    Embayment quality factor (0.3–1.0) based on beach openness vs wave energy demand.

    W = left_offset + right_offset (degrees) — the total angular window between headlands.
    A wider angle = more physically open beach (e.g. Long Reef at 90°).
    A narrower angle = more enclosed/closed beach (e.g. Freshwater at 57.5°).

    Wave Energy Demand = effective_height × (period² / 100).
    Longer-period groundswell carries more energy and needs more lateral room
    to spread out.  The /100 normalises so ratio clusters in a sensible range.

    Embayment Ratio = W / Demand

    High ratio (wide beach, small swell) → plenty of room → factor ≈ 1.0 (A-frame sweet spot)
    Low ratio (narrow beach, big swell) → close-out risk → factor ≈ 0.3
    """
    W = left_offset + right_offset
    demand = effective_height * (wave_period ** 2) / 100.0

    if demand <= 0:
        return 1.0

    ratio = W / demand

    # Breakpoints: (ratio, factor)
    # Calibrated so Freshwater on a 2.5m@14s day scores ~0.5,
    # while Long Reef on a 0.8m@8s day scores ~1.0.
    curve = [
        (0,   0.30),   # extreme close-out — wave has no room
        (10,  0.50),   # close-out zone
        (30,  0.80),   # marginal — some A-frame potential
        (60,  0.95),   # approaching ideal
        (100, 1.00),   # sweet spot — plenty of room
    ]

    for i in range(len(curve) - 1):
        x1, y1 = curve[i]
        x2, y2 = curve[i + 1]
        if x1 <= ratio <= x2:
            t = (ratio - x1) / (x2 - x1) if x2 != x1 else 0
            return y1 + t * (y2 - y1)

    if ratio > curve[-1][0]:
        return 1.0
    return curve[0][1]


def calculate_effective_height(offshore_height, wave_direction, beach_aspect, wave_period,
                              left_offset=10, right_offset=10):
    """
    Effective wave height after headland shadowing and period-driven shoaling.
    
    All multiplicative: offshore_swell × Kd × shoal_factor(period).
    Swell arriving within the L/R window is fully exposed (Kd=1).
    Beyond the window, Wiegel diffraction reduces the height.
    """
    diff = (wave_direction - beach_aspect + 180) % 360 - 180
    if -left_offset <= diff <= right_offset:
        shadow_angle = 0.0
    elif diff < -left_offset:
        shadow_angle = abs(diff) - left_offset
    else:
        shadow_angle = diff - right_offset

    kd = _diffraction_coefficient(shadow_angle)
    shoal = shoal_factor(wave_period)
    effective = offshore_height * kd * shoal

    if effective < 0.01:
        return 0.0
    return effective


def calculate_exposure_percent(wave_direction, beach_aspect,
                               left_offset=10, right_offset=10):
    """
    Beach exposure percentage = Kd × 100 (how much swell reaches the beach).
    """
    diff = (wave_direction - beach_aspect + 180) % 360 - 180
    if -left_offset <= diff <= right_offset:
        shadow_angle = 0
    elif diff < -left_offset:
        shadow_angle = abs(diff) - left_offset
    else:
        shadow_angle = diff - right_offset
    kd = _diffraction_coefficient(shadow_angle)
    return kd * 100


def calculate_wind_quality(wind_direction, beach_aspect, wind_speed_kmh=0):
    """
    Compute wind quality for a specific beach combining direction and speed.

    Uses a breakpoint table derived from the user's wind-speed quality specs:
    Speed      Offshore   Onshore   Description
    0–9 km/h    1.0       1.0      Glassy/calm — excellent regardless
    22 km/h     0.85      0.65     Light breeze — good offshore, fair onshore
    37 km/h     0.50      0.30     Moderate — poor to mediocre
    50+ km/h    0.25      0.15     Gale — dangerous/messy

    Values at intermediate speeds are linearly interpolated.  At any given speed,
    the final quality is a blend between offshore and onshore based on direction.
    """
    # Direction component
    delta = abs(wind_direction - beach_aspect)
    if delta > 180:
        delta = 360 - delta
    dir_quality = 1.0 - abs(delta - 180) / 180
    dir_quality = max(0.4, min(1.0, dir_quality))

    # Breakpoints: (speed_kmh, offshore_q, onshore_q)
    # Glassy calm → 0.85 (no wind to hold up the face)
    # Light offshore breeze → 1.0 (groomed, holds up the face)
    # Light onshore → 0.70 (some texture)
    bp = [
        (0,   0.85, 0.85),
        (9,   0.85, 0.85),
        (22,  1.00, 0.70),
        (37,  0.55, 0.35),
        (50,  0.25, 0.15),
    ]

    # Clamp speed and find surrounding breakpoints
    speed = max(0, min(wind_speed_kmh, 50))
    q_off = q_on = 1.0
    for i in range(len(bp) - 1):
        s1, off1, on1 = bp[i]
        s2, off2, on2 = bp[i + 1]
        if s1 <= speed <= s2:
            t = (speed - s1) / (s2 - s1) if s2 != s1 else 0
            q_off = off1 + t * (off2 - off1)
            q_on = on1 + t * (on2 - on1)
            break
    if speed > bp[-1][0]:
        q_off, q_on = bp[-1][1], bp[-1][2]

    # Blend offshore/onshore based on direction
    # dir_quality: 0.4 = onshore, 1.0 = offshore
    blend = (dir_quality - 0.4) / 0.6
    return q_on + (q_off - q_on) * blend


def wind_condition_label(wind_direction, beach_aspect):
    """
    Return a human-readable label for wind condition at a specific beach.
    """
    delta = abs(wind_direction - beach_aspect)
    if delta > 180:
        delta = 360 - delta
    if delta <= 30:
        return "Onshore"
    elif delta < 60:
        return "X-On"
    elif delta <= 120:
        return "Cross"
    elif delta < 150:
        return "X-Off"
    else:
        return "Offshore"


def wind_strength_emoji(wind_speed_kmh):
    """Emoji for wind speed thresholds:
    0–9 km/h  = glassy
    9–22 km/h = light breeze  🌬️
    22–37 km/h = moderate     💨
    37+ km/h   = gale/strong  🌪️"""
    if wind_speed_kmh < 9:
        return ""
    elif wind_speed_kmh < 22:
        return "🌬️"
    elif wind_speed_kmh < 37:
        return "💨"
    else:
        return "🌪️"


def calculate_surf_rating(effective_height, wave_period):
    """
    Calculate surf rating (0-5 stars) based on wave height and period.
    Height component: 0-2m maps to 0-2.5 points
    Period component: 6-16s maps to 0-2.5 points
    Tide factor modifies the final score
    """
    # Height component (0-2.5 points)
    height_points = min(2.5, (effective_height / 2.0) * 2.5)
    
    # Period component (0-2.5 points)
    # Assuming 6s = 0 points, 16s = 2.5 points, linear in between
    if wave_period < 6:
        period_points = 0
    elif wave_period > 16:
        period_points = 2.5
    else:
        period_points = ((wave_period - 6) / 10) * 2.5
    
    # Base score before tide factor
    base_score = height_points + period_points
    # Clamp to 0-5 range
    return max(0, min(5, base_score))


def tide_factor(tide_height):
    """
    Calculate tide factor multiplier.
    Optimal tide range: 0.5-1.5m -> factor = 1.0
    Outside this range, factor decreases linearly to 0.5 at 0m and 3.0m
    """
    if 0.5 <= tide_height <= 1.5:
        return 1.0
    elif tide_height < 0.5:
        return 0.6 + tide_height * (1.0 - 0.6) / 0.5  # 0.6 to 1.0
    else:  # tide_height > 1.5
        return 1.0 - (tide_height - 1.5) * (1.0 - 0.6) / (3.0 - 1.5)  # 1.0 to 0.6


def get_board_recommendation(effective_height, wave_period, wave_quality=1.0):
    """Get board recommendation(s) based on wave height, period, and quality.

    On poor quality days (onshore wind, ugly tide, bad angle), bumps volume up
    so you're hunting on a board that can actually catch the few good ones.
    Returns a comma-separated list of suitable board types."""

    # Quality-adjusted height for board selection:
    # Poor quality = treat the wave as smaller = recommend more volume
    # quality 1.0 → no adjustment; quality 0.2 → ~half the height for board pick
    quality_boost = 0.7 + wave_quality * 0.3    # ranges from 1.0 (perfect) down to 0.7 (terrible)
    adj_height = effective_height * quality_boost

    boards = []

    if adj_height < 0.3:
        boards = ["Longboard", "Log"]
    elif adj_height < 0.6:
        boards = ["Longboard", "Funboard"]
    elif adj_height < 1.0:
        boards = ["Groveller", "Fish", "Funboard"]
    elif adj_height < 1.5:
        boards = ["Shortboard", "Fish", "Mid-Length"]
    elif adj_height < 2.0:
        boards = ["Shortboard", "Mid-Length", "Step-Up"]
    elif adj_height < 2.5:
        boards = ["Shortboard", "Step-Up"]
    else:
        boards = ["Step-Up"]

    # Short period (< 8s) — weak/mushy swell, favour more volume
    if wave_period < 8:
        if "Step-Up" in boards:
            boards = ["Shortboard", "Fish"]
        elif "Shortboard" in boards:
            boards = ["Fish", "Funboard", "Mid-Length"]
        elif "Fish" in boards:
            boards = ["Mid-Length", "Funboard"]
        elif "Funboard" in boards or "Mid-Length" in boards:
            boards = ["Longboard", "Groveller"]
        else:
            boards = ["Longboard", "Log"]

    # Long period (>= 12s) — powerful ground swell, favour step-up when it's getting size
    elif wave_period >= 12 and adj_height >= 1.2:
        if adj_height < 1.5:
            boards = ["Shortboard", "Step-Up"]
        elif adj_height < 2.0:
            boards = ["Step-Up", "Shortboard"]
        elif adj_height < 2.5:
            boards = ["Step-Up"]
        else:
            boards = ["Step-Up"]

    # Remove duplicates and sort by board size (smallest first)
    seen = set()
    ordered = []
    for b in ["Shortboard", "Groveller", "Fish", "Step-Up", "Mid-Length", "Funboard", "Longboard", "Log"]:
        if b in boards and b not in seen:
            ordered.append(b)
            seen.add(b)
    
    return ", ".join(ordered)


def get_wetsuit_recommendation(month):
    """Get wetsuit recommendation based on month (fallback when real SST unavailable)."""
    return FALLBACK_WETSUIT_GUIDE.get(month, "Check local conditions")


def get_water_temperature(month):
    """Get approximate water temperature for month (fallback when real SST unavailable)."""
    return imos_sst.MONTHLY_SST.get(month, "Unknown")


def generate_stars(rating):
    """Generate HTML star rating."""
    full_stars = int(rating)
    half_star = 1 if rating - full_stars >= 0.5 else 0
    empty_stars = 5 - full_stars - half_star
    
    stars = '★' * full_stars
    if half_star:
        stars += '½'
    stars += '☆' * empty_stars
    return stars


def metres_to_feet_range(metres):
    """Convert metres to a display string in feet with range for in-between values.
    
    e.g. 0.6m -> 1-2 ft, 1.0m -> 3-4 ft, 2.0m -> 6-7 ft
    """
    feet = metres * 3.28084
    lower = int(feet)
    upper = lower + 1
    if lower == 0:
        lower = 1
    return f"{lower}-{upper} ft"


def compute_timeframe_conditions(marine_data, wind_data, tide_data, target_hour, today, sydney_tz, degrees_to_compass):
    """
    Compute all surf conditions for a single target hour.
    
    Returns a dict with:
      - label, emoji, hour
      - wave_height, wave_period, wave_direction, wave_compass
      - wind_speed, wind_direction, wind_compass, wind_knots
      - tide_height, display_tide, tide_trend, tide_emoji
      - beach_conditions: list of per-beach dicts
      - overall_rating, best_beaches_str, max_effective_height
      - wind_quality, attack_factor, tide_factor_value
    """
    # Extract hourly arrays
    marine_times = marine_data['hourly']['time']
    wave_heights = marine_data['hourly']['wave_height']
    wave_periods = marine_data['hourly']['wave_period']
    wave_directions = marine_data['hourly']['wave_direction']

    wind_times = wind_data['hourly']['time']
    wind_speeds = wind_data['hourly']['windspeed']
    wind_directions = wind_data['hourly']['winddirection']

    # Find indices for the target hour
    target_hour_str = f"{today}T{target_hour:02d}:00"
    try:
        marine_idx = marine_times.index(target_hour_str)
        wind_idx = wind_times.index(target_hour_str)
    except ValueError:
        marine_idx = 0
        wind_idx = 0
        logger.warning(f"Hour {target_hour}:00 not found in forecast data, using index 0")

    # Current conditions at this hour
    wave_height = wave_heights[marine_idx]
    wave_period = wave_periods[marine_idx]
    wave_direction = wave_directions[marine_idx]
    wind_speed = wind_speeds[wind_idx]
    wind_dir = wind_directions[wind_idx]
    wind_knots = wind_speed / 1.852

    # Tide at target hour
    target_dt = datetime.datetime(today.year, today.month, today.day, target_hour, 0, 0, tzinfo=sydney_tz)
    tide_height = tide_lookup(target_dt, tide_data)
    past_tide = tide_lookup(target_dt - datetime.timedelta(hours=1), tide_data)
    future_tide = tide_lookup(target_dt + datetime.timedelta(hours=1), tide_data)
    tide_trend = get_tide_trend(past_tide, tide_height, future_tide)

    tide_emoji_map = {
        "rising": "📈", "falling": "📉", "high": "🔺", "low": "🔻", "slack": "➖"
    }
    tide_emoji = tide_emoji_map.get(tide_trend, "")
    display_tide = -tide_height if tide_trend == "low" else tide_height

    wave_compass = degrees_to_compass(wave_direction)
    wind_compass = degrees_to_compass(wind_dir)

    # Calculate beach-specific conditions
    beach_conditions = []
    max_effective_height = 0

    for beach_name, bconfig in BEACHES.items():
        aspect = bconfig["aspect"]
        left_off = bconfig.get("left_offset", 10)
        right_off = bconfig.get("right_offset", 10)

        effective_height = calculate_effective_height(
            wave_height, wave_direction, aspect, wave_period, left_off, right_off
        )
        exposure = calculate_exposure_percent(wave_direction, aspect, left_off, right_off)

        # Angle of attack — how the swell hits the beach face
        # When swell is inside the window, attack = direct angular difference.
        # When outside, the wave diffracts around the headland and arrives
        # at roughly the window edge, so attack is clamped to the nearer offset.
        diff = (wave_direction - aspect + 180) % 360 - 180
        if -left_off <= diff <= right_off:
            attack_angle = abs(diff)
        elif diff < -left_off:
            attack_angle = left_off
        else:
            attack_angle = right_off
        attack_factor = _angle_of_attack_factor(attack_angle)

        # Wave Height score (0-5): power curve capped at 1.83m (6 ft / overhead)
        # Beyond 1.83m, height plateaus at 5★ — quality factors (wind, tide, attack) differentiate bigger waves
        wave_height_score = min(5, 5 * (effective_height / 1.83) ** 0.85)
        tide_factor_value = tide_factor(tide_height)

        bw_quality = calculate_wind_quality(wind_dir, aspect, wind_speed)
        bw_label = wind_condition_label(wind_dir, aspect)
        bw_strength = wind_strength_emoji(wind_speed)

        # Embayment factor — how open/closed the beach is for this swell
        embay_val = embayment_factor(left_off, right_off, effective_height, wave_period)

        # Wave Quality factor (0-1): product of wind, attack angle, tide, and embayment
        # If any factor is imperfect, quality drops — a product is stricter than an average
        wave_quality = bw_quality * attack_factor * tide_factor_value * embay_val

        adjusted_rating = wave_height_score * wave_quality
        adjusted_rating = max(0, min(5, adjusted_rating))
        precise_rating = adjusted_rating
        star_rating = round(precise_rating * 2) / 2
        board = get_board_recommendation(effective_height, wave_period, wave_quality)

        if effective_height > max_effective_height:
            max_effective_height = effective_height

        beach_conditions.append({
            "name": beach_name,
            "aspect": aspect,
            "effective_height": effective_height,
            "exposure": exposure,
            "rating": star_rating,
            "precise_rating": precise_rating,
            "board": board,
            "period": wave_period,
            "wind_quality": bw_quality,
            "wind_label": bw_label,
            "wind_strength": bw_strength,
            "wave_height_score": wave_height_score,
            "attack_factor": attack_factor,
            "attack_angle": attack_angle,
            "tide_factor_value": tide_factor_value,
            "embayment_factor": embay_val,
            "wave_quality": wave_quality,
        })

    # Overall rating — use the best beach's rating so it matches the top card
    overall_rating = max(bc["rating"] for bc in beach_conditions)

    # Best beaches — rating already bakes in wind, attack, and tide, so use directly
    best_score = max(bc["precise_rating"] for bc in beach_conditions)
    best_beaches = sorted(
        [bc for bc in beach_conditions if bc["precise_rating"] >= best_score - 0.5],
        key=lambda bc: bc["precise_rating"], reverse=True
    )[:3]
    best_beaches_str = ", ".join(bc["name"] for bc in best_beaches)

    return {
        "label": None,  # caller sets this
        "emoji": None,  # caller sets this
        "hour": target_hour,
        "wave_height": wave_height,
        "wave_period": wave_period,
        "wave_direction": wave_direction,
        "wave_compass": wave_compass,
        "wind_speed": wind_speed,
        "wind_direction": wind_dir,
        "wind_compass": wind_compass,
        "wind_knots": wind_knots,
        "tide_height": tide_height,
        "display_tide": display_tide,
        "tide_trend": tide_trend,
        "tide_emoji": tide_emoji,
        "beach_conditions": beach_conditions,
        "overall_rating": overall_rating,
        "best_beaches": best_beaches,
        "best_beaches_str": best_beaches_str,
        "max_effective_height": max_effective_height,
        # Solar data for UV and hat recommendations
        "solar_elevation": solar_elevation_azimuth(target_hour, today)[0],
        "solar_compass": degrees_to_compass(solar_elevation_azimuth(target_hour, today)[1]),
        "uv_index": uv_index(solar_elevation_azimuth(target_hour, today)[0]),
    }


def generate_report(marine_data, wind_data, tide_data):
    """Generate the complete multi-timeframe surf report HTML."""
    if not marine_data or not wind_data:
        return generate_error_report("Failed to fetch essential weather data")

    sydney_tz = datetime.timezone(datetime.timedelta(hours=10))  # AEST
    now = datetime.datetime.now(sydney_tz)
    today = now.date()

    # Define degrees_to_compass locally (used by compute_timeframe_conditions and template)
    def degrees_to_compass(degrees):
        directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                     "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        index = round(degrees / 22.5) % 16
        return directions[index]

    # Compute conditions for each timeframe
    all_timeframes = []
    for tf in TIMEFRAMES:
        cond = compute_timeframe_conditions(marine_data, wind_data, tide_data, tf["hour"], today, sydney_tz, degrees_to_compass)
        cond["label"] = tf["label"]
        cond["emoji"] = tf["emoji"]
        all_timeframes.append(cond)

    # Get SST data (shared across all timeframes)
    sst_data = imos_sst.get_water_temperature()
    water_temp = sst_data["temp"]
    sst_source = sst_data["source"]
    wetsuit_rec = imos_sst.get_wetsuit_recommendation(water_temp)

    # Generate LLM-powered per-beach reports (all timeframes in one call)
    llm_reports = llm_report.generate_reports(TIMEFRAMES, all_timeframes)
    if llm_reports:
        for tf in all_timeframes:
            for bc in tf["beach_conditions"]:
                bc["llm_note"] = llm_reports.get((tf["label"], bc["name"]), "")

    # Compute today's sunrise and sunset
    sunrise_hour, sunset_hour = sunrise_sunset(today)
    sunrise_str = f"{int(sunrise_hour):02d}:{int((sunrise_hour % 1) * 60):02d}"
    sunset_str = f"{int(sunset_hour):02d}:{int((sunset_hour % 1) * 60):02d}"

    # Build the timeframe section HTML blocks
    def build_tf_section(tf, is_first):
        display = "" if is_first else "display:none;"
        html = f'<div class="timeframe-content" data-tf="{tf["label"]}" style="{display}">'

        # Best Beaches section
        html += f'''
        <div class="section">
            <h2>🏆 Best Beaches</h2>
            <div class="summary-section">
                <div class="summary-item" style="grid-column: 1 / -1; text-align: center;">
                    <div class="stars" style="font-size: 1.8em; color: #ffd700; display: block; text-align: center;">{generate_stars(tf["overall_rating"])}</div>
                    <div style="font-weight: bold; color: #b8860b; font-size: 1.2em; margin-top: 4px;">{tf["best_beaches_str"]}</div>
                    <div style="margin-top: 6px; font-size: 0.9em; color: #555;">Biggest Break: <strong>{metres_to_feet_range(tf["max_effective_height"])}</strong></div>
                </div>
            </div>
        </div>'''

        # Overall Conditions section — two side-by-side cards
        uv = tf["uv_index"]
        hat_rec, uv_label = hat_recommendation(uv, tf["solar_compass"], "", [])
        html += f'''
        <div class="conditions-grid">
            <div class="section">
                <h2>🌊 Water Conditions</h2>
                <div class="condition-item">
                    <span class="label">Swell:</span>
                    <span class="value">{tf["wave_height"]:.1f}m @ {tf["wave_period"]:.0f}s from {tf["wave_direction"]:.0f}° ({tf["wave_compass"]})<span class="tooltip">Open-Meteo Marine API: global wave model (WW3) offshore Sydney</span></span>
                </div>
                <div class="condition-item">
                    <span class="label">Tide:</span>
                    <span class="value">{tf["display_tide"]:.1f}m {tf["tide_emoji"]} {tf["tide_trend"].title()}<span class="tooltip">Harmonic tide model (M2+S2 constituents) calibrated for Sydney Harbour</span></span>
                </div>
                <div class="condition-item">
                    <span class="label">Temp:</span>
                    <span class="value">{water_temp}°C — {wetsuit_rec}<span class="tooltip">{sst_source} — coastal edge SST off Northern Beaches</span></span>
                </div>
            </div>
            <div class="section">
                <h2>🌤️ Atmospheric</h2>
                <div class="condition-item">
                    <span class="label">Wind:</span>
                    <span class="value">{tf["wind_speed"]:.0f} km/h ({tf["wind_knots"]:.0f} kt) {tf["wind_compass"]}<span class="tooltip">Open-Meteo Weather API: 10m wind from GFS/ECMWF model</span></span>
                </div>
                <div class="condition-item">
                    <span class="label">Sun:</span>
                    <span class="value">🌅 {sunrise_str} — 🌇 {sunset_str} AEST<span class="tooltip">Sunrise/sunset times for Northern Beaches (calculated from latitude/longitude)</span></span>
                </div>
                <div class="condition-item">
                    <span class="label">UV:</span>
                    <span class="value">{uv_label} ({uv}) — Sun from {tf["solar_compass"]}<span class="tooltip">Estimated UV index based on solar elevation at this time</span></span>
                </div>
            </div>
        </div>
        <div class="section">
            <h2>🧤 Gear</h2>
            <div class="gear-grid">
                <div class="gear-item">
                    <div class="gear-icon">🩱</div>
                    <div class="gear-label">Wetsuit</div>
                    <div class="gear-value">{wetsuit_rec}</div>
                </div>
                <div class="gear-item">
                    <div class="gear-icon">🧢</div>
                    <div class="gear-label">Hat</div>
                    <div class="gear-value">{hat_rec}</div>
                </div>
            </div>
        </div>'''

        # Beach Conditions section
        html += '''
        <div class="section">
            <h2>🏖️ Beach Conditions</h2>
            <div class="beach-grid">'''

        best_names = {bc["name"] for bc in tf["best_beaches"]}
        for beach in tf["beach_conditions"]:
            stars = generate_stars(beach["rating"])
            is_best = beach["name"] in best_names
            card_class = " beach-card-best" if is_best else ""

            # Embayment warning emoji
            embay = beach["embayment_factor"]
            if embay < 0.50:
                embay_emoji = " 🚫"
            elif embay < 0.75:
                embay_emoji = " ⚠️"
            else:
                embay_emoji = ""

            html += f'''
                <div class="beach-card{card_class}">
                    <div class="beach-name">
                        <span>{beach["name"]}{embay_emoji}</span>
                        <span class="beach-aspect">{beach["aspect"]}° ({degrees_to_compass(beach["aspect"])})</span>
                    </div>
                    <div class="surf-info">
                        <div class="surf-detail">
                            <div class="surf-value">{metres_to_feet_range(beach["effective_height"])}</div>
                            <div class="surf-label">Height<span class="tooltip">Wave height at break</span></div>
                        </div>
                        <div class="surf-detail">
                            <div class="surf-value">{beach["attack_angle"]:.0f}°</div>
                            <div class="surf-label">AoA<span class="tooltip">Swell angle vs beach aspect</span></div>
                        </div>
                        <div class="surf-detail">
                            <div class="surf-value">{beach["exposure"]:.0f}%</div>
                            <div class="surf-label">Exposure<span class="tooltip">% swell after headland diffraction</span></div>
                        </div>
                        <div class="surf-detail">
                            <div class="surf-value">{beach["wind_label"]}</div>
                            <div class="surf-label">{beach["wind_strength"]} Wind<span class="tooltip">Wind vs beach aspect</span></div>
                        </div>
                    </div>
                    <div class="stars">{stars}'''
            if is_best:
                html += f' <span class="best-beach-badge">🏆 Best Beach</span>'
            html += f'''</div>
                        <div class="board">🏄 {beach["board"]}</div>'''
            if beach.get("llm_note"):
                html += f'''
                        <div class="forecaster-note">💬 {beach["llm_note"]}</div>'''
            html += '''
                    </div>'''

        html += '''
            </div>
        </div>'''
        html += '</div>\n'
        return html

    # Build the full HTML page
    first_tf_label = TIMEFRAMES[0]["label"]
    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Northern Beaches Surf Check</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 50px 20px 20px;
            background-color: #f0f8ff;
        }}
        header {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            z-index: 100;
            background: #f0f8ff;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 4px;
            padding: 6px 10px;
            border-bottom: 2px solid #0066cc;
        }}
        h1 {{
            color: #0066cc;
            font-size: 0.95em;
            margin: 0;
        }}
        .timeframe-nav {{
            display: flex;
            gap: 4px;
            flex-wrap: wrap;
            justify-content: center;
            width: 100%;
        }}
        .tf-btn {{
            padding: 4px 10px;
            border: 1.5px solid #0066cc;
            border-radius: 20px;
            background: white;
            color: #0066cc;
            font-size: 0.75em;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.15s, color 0.15s;
            white-space: nowrap;
        }}
        .tf-btn:hover {{
            background: #e6f2ff;
        }}
        .tf-btn.active {{
            background: #0066cc;
            color: white;
        }}
        .timestamp {{
            color: #666;
            font-style: italic;
            font-size: 0.6em;
            margin: 0;
        }}
        @media (min-width: 600px) {{
            body {{
                padding: 20px;
            }}
            header {{
                position: static;
                display: flex;
                flex-direction: column;
                padding: 20px 0 15px;
                margin-bottom: 30px;
            }}
            h1 {{
                font-size: 2.0em;
                margin-bottom: 8px;
            }}
            .timeframe-nav {{
                gap: 8px;
                margin-bottom: 6px;
            }}
            .tf-btn {{
                padding: 6px 18px;
                font-size: 0.9em;
            }}
            .timestamp {{
                font-size: 0.9em;
            }}
        }}
        .section {{
            background: white;
            margin-bottom: 25px;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h2 {{
            color: #0066cc;
            border-bottom: 2px solid #e6f2ff;
            padding-bottom: 10px;
            margin-bottom: 15px;
        }}
        .condition-item {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            padding: 10px;
            background-color: #f8f9fa;
            border-radius: 5px;
            cursor: help;
            border-bottom: 1px dashed #ccc;
        }}
        .label {{
            font-weight: 600;
            color: #555;
        }}
        .value {{
            font-weight: 500;
            color: #333;
            cursor: help;
            position: relative;
        }}
        .value .tooltip {{
            visibility: hidden;
            opacity: 0;
            position: absolute;
            bottom: calc(100% + 8px);
            left: 50%;
            transform: translateX(-50%);
            background: #333;
            color: #fff;
            padding: 6px 10px;
            border-radius: 6px;
            font-size: 0.8rem;
            font-weight: 400;
            white-space: nowrap;
            z-index: 10;
            pointer-events: none;
            transition: opacity 0.15s ease;
        }}
        .value .tooltip::after {{
            content: '';
            position: absolute;
            top: 100%;
            left: 50%;
            transform: translateX(-50%);
            border: 6px solid transparent;
            border-top-color: #333;
        }}
        .value:hover .tooltip {{
            visibility: visible;
            opacity: 1;
        }}
        .surf-label {{
            position: relative;
            cursor: help;
        }}
        .surf-label .tooltip {{
            visibility: hidden;
            opacity: 0;
            position: absolute;
            bottom: calc(100% + 4px);
            left: 50%;
            transform: translateX(-50%);
            background: #333;
            color: #fff;
            padding: 3px 7px;
            border-radius: 4px;
            font-size: 0.7rem;
            font-weight: 400;
            white-space: nowrap;
            z-index: 10;
            pointer-events: none;
        }}
        .surf-label:hover .tooltip {{
            visibility: visible;
            opacity: 1;
        }}
        .beach-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }}
        .beach-card {{
            border: 2px solid #e6f2ff;
            border-radius: 10px;
            padding: 15px;
            background-color: #f8f9fa;
        }}
        .beach-name {{
            font-size: 1.3em;
            font-weight: bold;
            color: #0066cc;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .beach-aspect {{
            font-size: 0.9em;
            color: #666;
            background: #e6f2ff;
            padding: 2px 6px;
            border-radius: 3px;
        }}
        .surf-info {{
            display: flex;
            justify-content: space-between;
            margin: 10px 0;
        }}
        .surf-detail {{
            text-align: center;
        }}
        .surf-value {{
            font-size: 1.5em;
            font-weight: bold;
            color: #0066cc;
        }}
        .surf-label {{
            font-size: 0.9em;
            color: #666;
        }}
        .beach-card .surf-info {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 4px;
        }}
        .beach-card .surf-detail .surf-value {{
            font-size: 1.1em;
            white-space: nowrap;
        }}
        .stars {{
            font-size: 1.2em;
            color: #ffd700;
            margin: 10px 0;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .board {{
            font-weight: bold;
            color: #8b4513;
            background: #f5deb3;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 0.9em;
        }}
        .forecaster-note {{
            font-size: 0.85em;
            color: #555;
            background: #f0fff0;
            padding: 6px 10px;
            border-radius: 6px;
            margin-top: 8px;
            border-left: 3px solid #4caf50;
            line-height: 1.4;
        }}
        .conditions-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 25px;
        }}
        .conditions-grid .section {{
            margin-bottom: 0;
        }}
        @media (max-width: 600px) {{
            .conditions-grid {{
                grid-template-columns: 1fr;
            }}
        }}
        .gear-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 15px;
        }}
        .gear-item {{
            text-align: center;
            padding: 15px;
            background: #f0f8ff;
            border-radius: 8px;
        }}
        .gear-icon {{
            font-size: 2em;
            margin-bottom: 6px;
        }}
        .gear-label {{
            font-size: 0.85em;
            color: #666;
            margin-bottom: 4px;
        }}
        .gear-value {{
            font-size: 1.1em;
            font-weight: bold;
            color: #0066cc;
        }}
        .summary-section {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }}
        .summary-item {{
            text-align: center;
            padding: 15px;
            background: #e6f2ff;
            border-radius: 8px;
        }}
        .summary-value {{
            font-size: 1.8em;
            font-weight: bold;
            color: #0066cc;
        }}
        .summary-label {{
            font-size: 0.9em;
            color: #555;
        }}
        .footer {{
            text-align: center;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            color: #666;
            font-size: 0.9em;
        }}
        .watermark {{
            position: fixed;
            bottom: 10px;
            right: 10px;
            font-size: 0.8em;
            color: #999;
            opacity: 0.7;
        }}
        .beach-card-best {{
            border-color: #ffd700;
            border-width: 3px;
            background: linear-gradient(135deg, #fffde7 0%, #fff8e1 100%);
        }}
        .best-beach-badge {{
            display: inline-block;
            background: #ffd700;
            color: #8b6914;
            font-size: 0.8em;
            font-weight: bold;
            padding: 2px 8px;
            border-radius: 10px;
            white-space: nowrap;
        }}
        @media (max-width: 599px) {{
            .timeframe-content {{
                margin-top: 10px;
            }}
        }}
    </style>
</head>
<body>
    <header>
        <h1>🏄‍♂️ Northern Beaches Surf Check</h1>'''

    # Timeframe navigation buttons
    html_content += '''
        <nav class="timeframe-nav">'''
    for i, tf in enumerate(TIMEFRAMES):
        active_class = ' active' if i == 0 else ''
        html_content += f'''
            <button class="tf-btn{active_class}" data-btn="{tf['label']}" onclick="showTimeframe('{tf['label']}')">{tf['emoji']} {tf['label']}</button>'''
    html_content += '''
        </nav>'''

    html_content += f'''
    </header>'''

    # All timeframe content blocks
    for i, tf in enumerate(all_timeframes):
        html_content += build_tf_section(tf, i == 0)

    # Footer, watermark, and JavaScript
    html_content += f'''
    <div class="footer">
        <p class="timestamp" style="margin-bottom: 12px; font-size: 0.9em;">Generated: {now.strftime('%Y-%m-%d %H:%M:%S')} AEST</p>
        <p><a href="./about.html" style="color: #0066cc; text-decoration: none; font-size: 0.9em;">About this site →</a></p>
        <p>Northern Beaches Surf Check - Automated surf report for Sydney beaches<br>
        Data sources: Open-Meteo (marine & wind forecasts), harmonic tide model, IMOS RAMSSA SST</p>
        <p>Report generated automatically for GitHub Pages deployment</p>
    </div>
    
    <div class="watermark">
        Northern Beaches Surf Check v2.0
    </div>

    <script>
        function showTimeframe(label) {{
            document.querySelectorAll('.timeframe-content').forEach(el => el.style.display = 'none');
            document.querySelectorAll('.tf-btn').forEach(el => el.classList.remove('active'));
            const content = document.querySelector('.timeframe-content[data-tf="' + label + '"]');
            if (content) content.style.display = 'block';
            const btn = document.querySelector('.tf-btn[data-btn="' + label + '"]');
            if (btn) btn.classList.add('active');
            try {{ localStorage.setItem('surfcheckTimeframe', label); }} catch(e) {{}}
        }}
        document.addEventListener('DOMContentLoaded', function() {{
            const saved = (function(){{ try {{ return localStorage.getItem('surfcheckTimeframe'); }} catch(e){{ return null; }} }})();
            if (saved && document.querySelector('.timeframe-content[data-tf="' + saved + '"]')) {{
                showTimeframe(saved);
            }}
        }});
    </script>
</body>
</html>'''

    return html_content


def generate_error_report(error_message):
    """Generate a simple error report when data fetching fails."""
    sydney_tz = datetime.timezone(datetime.timedelta(hours=10))
    now = datetime.datetime.now(sydney_tz)
    
    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Northern Beaches Surf Check - Service Temporarily Unavailable</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 40px 20px;
            background-color: #fff8f0;
            text-align: center;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 0 20px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #d35400;
            margin-bottom: 20px;
        }}
        .message {{
            font-size: 1.2em;
            color: #555;
            margin-bottom: 30px;
        }}
        .details {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            margin-top: 20px;
            text-align: left;
        }}
        .footer {{
            margin-top: 30px;
            color: #888;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>⚠️ Service Temporarily Unavailable</h1>
        <div class="message">
            Unable to generate surf report at this time.
        </div>
        <div class="details">
            <p><strong>Time:</strong> {now.strftime('%Y-%m-%d %H:%M:%S')} AEST</p>
            <p><strong>Error:</strong> {error_message}</p>
            <p>The service will automatically retry on the next scheduled update.</p>
        </div>
        <div class="footer">
            <p>Northern Beaches Surf Check - Data sources: Open-Meteo (marine & wind forecasts), MHL (tide observations)</p>
            <p>This is an automated service - please try again later.</p>
        </div>
    </div>
</body>
</html>'''
    
    return html_content


def main():
    """Main function to generate and save the surf report."""
    logger.info("Starting surf report generation")
    
    # Fetch data
    logger.info("Fetching marine forecast...")
    marine_data = fetch_marine_forecast()
    
    logger.info("Fetching wind forecast...")
    wind_data = fetch_wind_forecast()
    
    logger.info("Fetching tide data...")
    tide_data = fetch_current_tide_from_mhl()
    
    # Generate report
    if marine_data and wind_data:
        logger.info("Generating surf report...")
        html_content = generate_report(marine_data, wind_data, tide_data)
        report_file = REPORT_FILE
        logger.info(f"Saving report to {report_file}")
    else:
        error_msg = "Failed to fetch required weather data"
        logger.error(error_msg)
        html_content = generate_error_report(error_msg)
        report_file = REPORT_FILE
    
    # Ensure docs directory exists
    report_file.parent.mkdir(exist_ok=True)
    
    # Write report
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info(f"Report successfully written to {report_file}")
        
        # Also create a simple text log of the generation
        log_file = Path.home() / "surf_report_log.txt"
        with open(log_file, 'a') as f:
            f.write(f"{datetime.datetime.now()}: Report generated successfully\n")

        return True
    except Exception as e:
        logger.error(f"Failed to write report: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)