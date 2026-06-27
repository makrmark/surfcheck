#!/usr/bin/env python3
"""
Surforecast - Automated Surf Report Generator for GitHub Pages

Generates a daily surf report for NSW beaches and publishes it as a static HTML page
to trigger GitHub Pages deployment.
"""

import requests
import datetime
import math
import os
import sys
import logging
from pathlib import Path

# Configuration
LOCATION = {"latitude": -33.78, "longitude": 151.30}  # Sydney
REPORT_TIME_HOUR = 6  # 6:00 AM report time
BEACHES = {
    "Long Reef": 158,   # degrees from North (sse)
    "Dee Why": 135,     # degrees from North (southeast)
    "Curl Curl": 112,   # degrees from North (east-southeast)
    "Freshwater": 135,  # degrees from North (southeast)
    "North Steyne": 90, # degrees from North (east)
    "South Steyne": 68  # degrees from North (east-northeast)
}
BEACH_NOTES = {
    "Long Reef": "Northernmost beach, southeast-southeast exposure",
    "Dee Why": "Southeast facing beach, sheltered by southern headland",
    "Curl Curl": "East-southeast exposed beach with consistent swell",
    "Freshwater": "Southeast facing beach, protected by northern headland",
    "North Steyne": "Eastern end of Manly Beach, exposed to east swells",
    "South Steyne": "East-northeast end of Manly Beach, NE swell exposure"
}
LOG_FILE = Path.home() / "surforecast.log"
REPORT_FILE = Path("docs") / "index.html"  # GitHub Pages serves from /docs
ERROR_REPORT_FILE = Path("docs") / "error.html"

# Wetsuit guide by month (Southern Hemisphere)
WETSUIT_GUIDE = {
    12: "Boardshorts or rash vest",
    1: "Boardshorts or rash vest", 
    2: "Boardshorts or rash vest",
    3: "Spring suit (2mm)",
    4: "Spring suit (2mm)",
    5: "3/2 full wetsuit",
    6: "4/3 full wetsuit",
    7: "4/3 full wetsuit",
    8: "4/3 full wetsuit",
    9: "3/2 full wetsuit",
    10: "3/2 full wetsuit",
    11: "Spring suit (2mm)",
    12: "Boardshorts or rash vest"
}

# Sea temperature by month (Southern Hemisphere, approximate)
SEA_TEMPERATURE = {
    12: 22, 1: 22, 2: 22,  # Summer
    3: 20, 4: 20, 5: 20,   # Autumn
    6: 16, 7: 16, 8: 16,   # Winter
    9: 21, 10: 21, 11: 21  # Spring
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


def calculate_effective_height(offshore_height, wave_direction, beach_aspect, wave_period):
    """
    Calculate wave height at breaking using the breaker index formula:
    H ≈ 0.44 · H₀ · (T / √H₀)^(2/5)
    
    First computes the directional exposure (effective offshore height),
    then estimates the wave height right before breaking.
    
    Parameters:
    - offshore_height: deep-water swell height in metres (H₀)
    - wave_direction: direction of swell in degrees from north
    - beach_aspect: direction the beach faces in degrees from north
    - wave_period: swell period in seconds (T)
    
    Returns:
    - estimated breaker wave height in metres
    """
    # Step 1: Calculate directional exposure factor
    delta_theta = math.radians(abs(wave_direction - beach_aspect))
    exposure_factor = max(0, math.cos(delta_theta))
    
    # Step 2: Effective offshore height at the beach
    h0_effective = offshore_height * exposure_factor
    
    # Step 3: If there's no significant wave energy, return 0
    if h0_effective < 0.01 or wave_period < 1:
        return 0.0
    
    # Step 4: Apply the breaker formula
    # H = 0.44 · H₀ · (T / √H₀)^(2/5)
    h_breaker = 0.44 * h0_effective * (wave_period / (h0_effective ** 0.5)) ** 0.4
    
    return h_breaker


def calculate_exposure_percent(wave_direction, beach_aspect):
    """
    Calculate beach exposure percentage.
    exposure = (90 - |Δθ|) / 90 * 100, clamped to [0, 100]
    """
    delta_theta = abs(wave_direction - beach_aspect)
    exposure = max(0, min(100, (90 - delta_theta) / 90 * 100))
    return exposure


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
        return 0.5 + (tide_height - 0) * (1.0 - 0.5) / (0.5 - 0)  # 0.5 to 1.0
    else:  # tide_height > 1.5
        return 1.0 - (tide_height - 1.5) * (1.0 - 0.5) / (3.0 - 1.5)  # 1.0 to 0.5


def get_board_recommendation(effective_height, wave_period):
    """Get board recommendation(s) based on wave height and period.
    Returns a comma-separated list of suitable board types."""
    boards = []

    if effective_height < 0.3:
        boards = ["Longboard", "Log"]
    elif effective_height < 0.6:
        boards = ["Longboard", "Funboard"]
    elif effective_height < 1.0:
        boards = ["Fish", "Funboard", "Mid-Length", "Groveller"]
    elif effective_height < 1.5:
        boards = ["Shortboard", "Fish"]
    elif effective_height < 2.0:
        boards = ["Shortboard", "Step-Up"]
    else:
        boards = ["Step-Up", "Shortboard"]

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
    elif wave_period >= 12 and effective_height >= 1.2:
        if effective_height < 1.5:
            boards = ["Shortboard", "Step-Up"]
        elif effective_height < 2.0:
            boards = ["Step-Up", "Shortboard"]
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
    """Get wetsuit recommendation based on month."""
    return WETSUIT_GUIDE.get(month, "Check local conditions")


def get_water_temperature(month):
    """Get approximate water temperature for month."""
    return SEA_TEMPERATURE.get(month, "Unknown")


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


def generate_report(marine_data, wind_data, tide_data):
    """Generate the complete surf report HTML."""
    if not marine_data or not wind_data:
        return generate_error_report("Failed to fetch essential weather data")
    
    # Get current time in Sydney timezone
    sydney_tz = datetime.timezone(datetime.timedelta(hours=10))  # AEST
    now = datetime.datetime.now(sydney_tz)
    today = now.date()
    
    # Extract marine data
    marine_times = marine_data['hourly']['time']
    wave_heights = marine_data['hourly']['wave_height']
    wave_periods = marine_data['hourly']['wave_period']
    wave_directions = marine_data['hourly']['wave_direction']
    
    # Extract wind data
    wind_times = wind_data['hourly']['time']
    wind_speeds = wind_data['hourly']['windspeed']
    wind_directions = wind_data['hourly']['winddirection']
    
    # Find indices for report time (6:00 AM today)
    target_hour_str = f"{today}T{REPORT_TIME_HOUR:02d}:00"
    try:
        marine_idx = marine_times.index(target_hour_str)
        wind_idx = wind_times.index(target_hour_str)
    except ValueError:
        # Fallback to current hour if exact time not available
        current_hour_str = f"{today}T{now.hour:02d}:00"
        marine_idx = marine_times.index(current_hour_str) if current_hour_str in marine_times else 0
        wind_idx = wind_times.index(current_hour_str) if current_hour_str in wind_times else 0
    
    # Get current conditions
    current_wave_height = wave_heights[marine_idx]
    current_wave_period = wave_periods[marine_idx]
    current_wave_direction = wave_directions[marine_idx]
    current_wind_speed = wind_speeds[wind_idx]
    current_wind_direction = wind_directions[wind_idx]
    wind_knots = current_wind_speed / 1.852
    
    # Get tide information
    tide_height = tide_lookup(now, tide_data)
    # Get tide trend by checking a few hours before and after
    past_time = now - datetime.timedelta(hours=1)
    future_time = now + datetime.timedelta(hours=1)
    past_tide = tide_lookup(past_time, tide_data)
    future_tide = tide_lookup(future_time, tide_data)
    tide_trend = get_tide_trend(past_tide, tide_height, future_tide)
    # Determine display tide height (negative for low tide)
    display_tide = -tide_height if tide_trend == "low" else tide_height
    # Determine tide emoji
    tide_emoji_map = {
        "rising": "📈",
        "falling": "📉",
        "high": "🔺",
        "low": "🔻",
        "slack": "➖"
    }
    tide_emoji = tide_emoji_map.get(tide_trend, "")
    
    # Determine compass directions
    def degrees_to_compass(degrees):
        directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                     "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        index = round(degrees / 22.5) % 16
        return directions[index]
    
    wave_compass = degrees_to_compass(current_wave_direction)
    wind_compass = degrees_to_compass(current_wind_direction)
    
    # Get month for wetsuit recommendation
    month = now.month
    wetsuit_rec = get_wetsuit_recommendation(month)
    water_temp = get_water_temperature(month)
    
    # Calculate beach-specific conditions
    beach_conditions = []
    max_effective_height = 0
    
    for beach_name, aspect in BEACHES.items():
        effective_height = calculate_effective_height(
            current_wave_height, current_wave_direction, aspect, current_wave_period
        )
        exposure = calculate_exposure_percent(current_wave_direction, aspect)
        rating = calculate_surf_rating(effective_height, current_wave_period)
        # Apply tide factor to rating
        tide_factor_value = tide_factor(tide_height)
        adjusted_rating = rating * tide_factor_value
        # Clamp rating to 0-5
        adjusted_rating = max(0, min(5, adjusted_rating))
        # Store precise rating for ranking, and star-rounded for display
        precise_rating = adjusted_rating
        star_rating = round(precise_rating * 2) / 2
        board = get_board_recommendation(effective_height, current_wave_period)
        
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
            "notes": BEACH_NOTES.get(beach_name, ""),
            "period": current_wave_period
        })
    
    # Overall rating (average of beach star ratings, rounded to nearest half star)
    overall_rating = sum(bc["rating"] for bc in beach_conditions) / len(beach_conditions)
    overall_rating = max(0, min(5, overall_rating))
    overall_rating = round(overall_rating * 2) / 2
    
    # Determine wind quality factor (offshore vs onshore wind)
    # Offshore wind = wind opposite to wave direction (clean waves)
    # Onshore wind = wind same as wave direction (choppy waves)
    wind_wave_angle = abs(current_wind_direction - current_wave_direction)
    if wind_wave_angle > 180:
        wind_wave_angle = 360 - wind_wave_angle
    # quality: 1.0 = perfect offshore (opposite), 0.0 = onshore (same direction)
    wind_quality = 1.0 - abs(wind_wave_angle - 180) / 180
    
    # Determine tide quality factor (how tide stage affects surf quality)
    # Rising tide acts as a "push", organizing swell -> bonus
    # High tide can drown out waves -> penalty
    # Low tide = steeper/faster waves but harder paddle out -> slight penalty
    # Falling tide can generate rips -> slight penalty
    tide_quality_map = {
        "rising": 1.1,   # incoming tide organizes swell
        "falling": 0.95,  # outgoing can create rips
        "high": 0.85,     # high tide can drown out waves
        "low": 0.95,      # steeper waves but dangerous shore break
        "slack": 1.0,     # neutral
        "changing": 1.0   # neutral
    }
    tide_quality = tide_quality_map.get(tide_trend, 1.0)
    
    # Determine best beaches using composite score (precise rating × wind quality × tide quality)
    composite_for_beach = lambda bc: bc["precise_rating"] * (0.5 + 0.25 * wind_quality + 0.25 * tide_quality)
    best_score = max(composite_for_beach(bc) for bc in beach_conditions)
    best_beaches = sorted(
        [bc for bc in beach_conditions if composite_for_beach(bc) >= best_score - 0.5],
        key=composite_for_beach,
        reverse=True
    )[:3]
    best_beaches_str = ", ".join(bc["name"] for bc in best_beaches)
    
    # Generate HTML
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
            align-items: baseline;
            justify-content: center;
            gap: 8px;
            padding: 8px 10px;
            border-bottom: 2px solid #0066cc;
        }}
        h1 {{
            color: #0066cc;
            font-size: 1.0em;
            margin: 0;
        }}
        .timestamp {{
            color: #666;
            font-style: italic;
            font-size: 0.65em;
            margin: 0;
        }}
        @media (min-width: 600px) {{
            body {{
                padding: 20px;
            }}
            header {{
                position: static;
                display: block;
                padding: 25px 0 15px;
                margin-bottom: 30px;
            }}
            h1 {{
                font-size: 2.2em;
                margin-bottom: 10px;
            }}
            .timestamp {{
                font-size: 1em;
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
        }}
        .label {{
            font-weight: 600;
            color: #555;
        }}
        .value {{
            font-weight: 500;
            color: #333;
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
        .stars {{
            font-size: 1.2em;
            color: #ffd700;
            margin: 10px 0;
        }}
        .board {{
            font-weight: bold;
            color: #8b4513;
            background: #f5deb3;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 0.9em;
        }}
        .notes {{
            font-size: 0.9em;
            font-style: italic;
            color: #666;
            margin-top: 10px;
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
            font-size: 0.75em;
            font-weight: bold;
            padding: 2px 8px;
            border-radius: 10px;
            margin-top: 8px;
        }}
    </style>
</head>
<body>
    <header>
        <h1>🏄‍♂️ Northern Beaches Surf Check</h1>
        <p class="timestamp">Generated: {now.strftime('%Y-%m-%d %H:%M:%S')} AEST</p>
    </header>

    <div class="section">
        <h2>🏆 Best Beaches</h2>
        <div class="summary-section">
            <div class="summary-item" style="grid-column: 1 / -1;">
                <div style="font-weight: bold; color: #b8860b; font-size: 1.2em;">{best_beaches_str}</div>
                <div class="stars" style="font-size: 1.5em; margin-top: 6px; color: #ffd700;">{generate_stars(overall_rating)}</div>
                <div style="margin-top: 8px; font-size: 0.9em; color: #555;">Biggest Break: <strong>{max_effective_height:.1f}m</strong></div>
            </div>
        </div>
    </div>

    <div class="section">
        <h2>🌊 Overall Conditions</h2>
        <div class="condition-item">
            <span class="label">Swell:</span>
            <span class="value">{current_wave_height:.1f}m @ {current_wave_period:.0f}s from {current_wave_direction:.0f}° ({wave_compass})</span>
        </div>
        <div class="condition-item">
            <span class="label">Wind:</span>
            <span class="value">{current_wind_speed:.0f} km/h ({wind_knots:.0f} kt) {wind_compass}</span>
        </div>
        <div class="condition-item">
            <span class="label">Tide:</span>
            <span class="value">{display_tide:.1f}m {tide_emoji} {tide_trend.title()}</span>
        </div>
        <div class="condition-item">
            <span class="label">Water:</span>
            <span class="value">{water_temp}°C — {wetsuit_rec}</span>
        </div>
    </div>

    <div class="section">
        <h2>🏖️ Beach Conditions</h2>
        <div class="beach-grid">
'''
    
    for beach in beach_conditions:
        stars = generate_stars(beach["rating"])
        best_names = {bc["name"] for bc in best_beaches}
        is_best = beach["name"] in best_names
        best_card_class = " beach-card-best" if is_best else ""
        html_content += f'''
            <div class="beach-card{best_card_class}">
                <div class="beach-name">
                    <span>{beach["name"]}</span>
                    <span class="beach-aspect">{beach["aspect"]}° ({degrees_to_compass(beach["aspect"])})</span>
                </div>
                <div class="surf-info">
                    <div class="surf-detail">
                        <div class="surf-value">{beach["effective_height"]:.1f}m</div>
                        <div class="surf-label">Surf Height</div>
                    </div>
                    <div class="surf-detail">
                        <div class="surf-value">{beach["period"]:.0f}s</div>
                        <div class="surf-label">Period</div>
                    </div>
                    <div class="surf-detail">
                        <div class="surf-value">{beach["exposure"]:.0f}%</div>
                        <div class="surf-label">Exposure</div>
                    </div>
                </div>
                <div class="stars">{stars}</div>
                <div class="board">🏄 {beach["board"]}</div>
                <div class="notes">{beach["notes"]}</div>
            </div>''' if not is_best else f'''
            <div class="beach-card{best_card_class}">
                <div class="beach-name">
                    <span>{beach["name"]}</span>
                    <span class="beach-aspect">{beach["aspect"]}° ({degrees_to_compass(beach["aspect"])})</span>
                </div>
                <div class="surf-info">
                    <div class="surf-detail">
                        <div class="surf-value">{beach["effective_height"]:.1f}m</div>
                        <div class="surf-label">Surf Height</div>
                    </div>
                    <div class="surf-detail">
                        <div class="surf-value">{beach["period"]:.0f}s</div>
                        <div class="surf-label">Period</div>
                    </div>
                    <div class="surf-detail">
                        <div class="surf-value">{beach["exposure"]:.0f}%</div>
                        <div class="surf-label">Exposure</div>
                    </div>
                </div>
                <div class="stars">{stars}</div>
                <div class="board">🏄 {beach["board"]}</div>
                <div class="best-beach-badge">⭐ Best Beach Today</div>
                <div class="notes">{beach["notes"]}</div>
            </div>'''
    
    html_content += f'''
        </div>
    </div>

    

    <div class="footer">
        <p><a href="./about.html" style="color: #0066cc; text-decoration: none; font-size: 0.9em;">About this site →</a></p>
        <p>Northern Beaches Surf Check - Automated surf report for Sydney beaches<br>
        Data sources: Open-Meteo (marine & wind forecasts), MHL (tide observations)</p>
        <p>Report generated automatically for GitHub Pages deployment</p>
    </div>
    
    <div class="watermark">
        Northern Beaches Surf Check v1.0
    </div>
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