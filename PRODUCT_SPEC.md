# Product Specification – Surforecast Static Webpage

**Version:** 1.0  
**Date:** 2026-06-26  
**Author:** Updated from Hermes Agent spec for static webpage deployment  

---  

## 1. Overview  

Surforecast is a static webpage that provides daily surf reports for NSW beaches. The system runs automatically each morning, fetches live marine and meteorological data, processes it into a surf report, and publishes a static HTML page to GitHub Pages. The system runs via a local cron job that runs the generation script and commits/pushes the updated page to trigger GitHub Pages deployment.

---  

## 2. Goals  

| Goal | Description |
|------|-------------|
| **Timeliness** | Generate and deploy a fresh report every day before typical morning surf session (06:00 LT). |
| **Accuracy** | Use authoritative sources (MHL tide, Open-Meteo marine/wind forecasts) and physics-based tide calculations. |
| **Actionable Information** | Display wave height, period, direction, tide height & trend, beach-specific conditions, ratings, and wetsuit recommendations. |
| **Reliability** | Graceful fallback to harmonic tide model if live tide API fails; logging and error reporting. |
| **Automation** | Fully automated daily update via local cron job that commits to GitHub to trigger Pages deployment. |
| **Static Deployment** | Generated HTML page hosted on GitHub Pages for fast, reliable delivery. |
| **Extensibility** | Easy to add new beaches, adjust rating thresholds, or modify display formatting. |

---  

## 3. Functional Requirements  

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| **FR-1** | **Data Acquisition** – Retrieve marine forecast (wave height, period, direction) and wind forecast (speed, direction) from Open-Meteo APIs for Sydney coordinates (-33.78, 151.30). | Successful HTTP 200 responses; parsed JSON contains required hourly fields. |
| **FR-2** | **Tide Observation** – Query MHL Station 213470 (Sydney Level 1) for current water-level observation and timestamp. | Returns numeric tide height (metres) and valid ISO-8601 timestamp; on failure, logs warning and falls back to harmonic tide model. |
| **FR-3** | **Tide Forecast** – Using observed tide height & timestamp, compute tide height and trend (rising/falling/high/low) for report time (06:00) and 3-hour forecast slots (06, 09, 12, 15, 18h). | Computed values within ±0.2m of reference tide table (when MHL data available); trend matches numerical derivative sign. |
| **FR-4** | **Beach-Specific Wave Height** – For each beach (Collaroy, Freshwater, Manly), compute effective height = offshore height × cos(Δθ), where Δθ is absolute difference between beach aspect (° from N) and wave direction. | Effective height ≥ 0 and ≤ offshore height; exposure % = (90‑\|Δθ\|)/90 × 100 clamped to [0,100]. |
| **FR-5** | **Surf Rating** – Calculate 0‑5 star rating based on effective wave height (scaled to 2m max) and wave period (scaled 6‑15s), multiplied by tide factor (optimal tide 0.5‑1.5m → 1.0; outside range reduces linearly). | Rating matches specification table (see Section 4.1). |
| **FR-6** | **Board Recommendation** – Map effective height to board type (Log < 0.5m, Funboard 0.5‑1.0m, Shortboard 1.0‑2.0m, Gun > 2.0m) with dual‑option handling when height within 0.1m of threshold; adjust down one step if period < 8s. | Recommendation string follows rule set; examples: 0.45m → Log, 0.95m → Funboard/Shortboard, 2.2m → Gun. |
| **FR-7** | **Wetsuit Recommendation** – Based on month-derived sea‑surface temperature (see Table 1) and Quiksilver guide, output textual recommendation (e.g., “Boardshorts or rash vest”, “Spring suit (2mm)”, “3/2 full wetsuit”, “4/3 full wetsuit with booties, gloves, hood”). | Recommendation matches decision table for given month. |
| **FR-8** | **Report Generation** – Produce a static HTML surf report with sections: header, offshore swell, wind, per‑beach cards (beach [aspect° (dir)] Surf: X.Xm [Ys @ Z%] ★★☆☆☆ Board: A/B), overall summary, max expected tide, water temp & wetsuit recommendation, timestamp. | Generated HTML matches template in Section 5 and is valid HTML5. |
| **FR-9** | **Automated Deployment** – Local cron job runs generation script daily at 05:45 LT, commits updated HTML to git repo, and pushes to origin to trigger GitHub Pages rebuild. | Job runs successfully each morning; GitHub Pages updates within minutes of push; commit history shows daily updates. |
| **FR-10** | **Logging & Error Handling** – Script logs operations and errors to local log file; on critical failures, generates error HTML page indicating issue. | Logs contain timestamps and error details; fallback error page is valid HTML. |

---  

## 4. Data Sources & Calculations  

### 4.1 Data Sources  
- **Open-Meteo Marine API**: https://marine-api.open-meteo.com/v1/marine  
  Parameters: latitude=-33.78, longitude=151.30, hourly=wave_height,wave_period,wave_direction,wind_speed,wind_direction  
- **Open-Meteo Weather API**: https://api.open-meteo.com/v1/forecast  
  Parameters: latitude=-33.78, longitude=151.30, hourly=temperature_2m,weathercode  
- **Manly Hydraulics Laboratory (MHL) API**: https://mhl.nsw.gov.au/Data/SeaLevel/Data/TimeSeries/213470.csv  
  Returns CSV with timestamp and sea level values  

### 4.2 Beach Definitions  

| Beach | Aspect (° from North) | Notes |
|-------|----------------------|-------|
| Collaroy | 90° (East) | Faces due east |
| Freshwater | 100° (East-Southeast) | Slight southward orientation |
| Manly | 110° (East-Southeast) | More southerly exposure |

### 4.3 Surf Rating Formula  

The rating combines three normalized factors:  
1. **Wave Height Factor**: min(effective_height / 2.0, 1.0)  
2. **Period Factor**: min((wave_period - 6) / (15 - 6), 1.0) clamped to [0,1]  
3. **Tide Factor**:  
   - If 0.5 ≤ tide_height ≤ 1.5: factor = 1.0  
   - If tide_height < 0.5: factor = tide_height / 0.5  
   - If tide_height > 1.5: factor = max(0, (3.0 - tide_height) / 1.5)  

Final Rating = 5 × (Height Factor × Period Factor × Tide Factor)  
Rounded to nearest 0.5 star, displayed as ★★☆☆☆ (full stars for integer part, half star for .5)

### 4.4 Wetsuit Guide (by Month)  

| Month | Approx. Water Temp | Wetsuit Recommendation |
|-------|-------------------|------------------------|
| Dec-Feb | 20-24°C | Boardshorts or rash vest |
| Mar, Nov | 18-20°C | Spring suit (2mm) or springsuit |
| Apr-May | 16-18°C | 3/2 full wetsuit |
| Jun-Aug | 14-16°C | 4/3 full wetsuit |
| Sep-Oct | 16-19°C | 3/2 full wetsuit |

---  

## 5. Report Template (HTML Structure)  

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Surforecast - Sydney Surf Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f0f8ff; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        h1 { color: #0066cc; text-align: center; }
        .timestamp { text-align: center; color: #666; font-style: italic; margin-bottom: 20px; }
        .section { margin: 20px 0; padding: 15px; border-left: 4px solid #0066cc; background: #f8f9fa; }
        .beach-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; margin: 15px 0; }
        .beach-card { border: 1px solid #ddd; border-radius: 8px; padding: 15px; background: white; }
        .beach-name { font-weight: bold; font-size: 1.1em; margin-bottom: 10px; }
        .surf-info { margin: 8px 0; }
        .rating { font-size: 1.2em; letter-spacing: 2px; }
        .board { font-weight: bold; color: #0066cc; }
        .tide-info, .wetsuit-info { background: #e3f2fd; padding: 10px; border-radius: 5px; margin: 10px 0; }
        .footer { text-align: center; margin-top: 30px; color: #666; font-size: 0.9em; border-top: 1px solid #eee; padding-top: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Surforecast - Sydney Surf Report</h1>
        <div class="timestamp">Last updated: {timestamp}</div>
        
        <div class="section">
            <h2>Offshore Conditions</h2>
            <div class="surf-info"><strong>Swell:</strong> {swell_height}m @ {swell_period}s from {swell_direction}°</div>
            <div class="surf-info"><strong>Wind:</strong> {wind_speed}km/h from {wind_direction}° ({wind_direction_text})</div>
        </div>
        
        <div class="section">
            <h2>Beach Conditions</h2>
            <div class="beach-grid">
                {beach_cards}
            </div>
        </div>
        
        <div class="section">
            <h2>Overall Assessment</h2>
            <div class="surf-info"><strong>Overall Rating:</strong> {overall_rating}</div>
            <div class="surf-info"><strong>Max Expected Tide:</strong> {max_tide}m ({tide_trend})</div>
        </div>
        
        <div class="section">
            <h2>Water Temperature & Wetsuit Guide</h2>
            <div class="wetsuit-info">
                <strong>Water Temperature:</strong> {water_temp}°C<br>
                <strong>Recommended Wetsuit:</strong> {wetsuit_recommendation}
            </div>
        </div>
        
        <div class="footer">
            Surforecast - Automated surf report for Sydney beaches<br>
            Data sources: Open-Meteo, MHL NSW<br>
            Generated daily at 05:45 AM for morning surf sessions
        </div>
    </div>
</body>
</html>
```

---  

## 6. Non-Functional Requirements  

| Requirement | Description |
|-------------|-------------|
| **Performance** | Report generation completes within 30 seconds; HTML page loads in <2 seconds on standard connection. |
| **Reliability** | Script includes error handling and fallback mechanisms; generates error page if critical data unavailable. |
| **Maintainability** | Modular Python script with clear separation of data fetching, processing, and HTML generation. |
| **Deployment** | Simple git push triggers GitHub Pages update; no external hosting required. |
| **Monitoring** | Local logs track script execution; GitHub commit history provides deployment audit trail. |

---  

## 7. Implementation Plan  

### 7.1 Local Setup  
1. Create project directory: `~/surforecast`  
2. Initialize git repository: `git init`  
3. Create Python script: `surforecast.py`  
4. Create README with setup instructions  
5. Set up local cron job (or launch agent) to run daily at 05:45  

### 7.2 Script Components  
1. **Data Fetching Module**: Handles API calls to Open-Meteo and MHL  
2. **Processing Module**: Calculates tide forecasts, beach-specific conditions, ratings, recommendations  
3. **HTML Generation Module**: Populates HTML template with processed data  
4. **Git Integration Module**: Commits changes and pushes to origin  
5. **Main Controller**: Orchestrates flow and handles errors  
6. **Logging Module**: Logs operations to local file  

### 7.3 Deployment Configuration  
1. Create GitHub repository: `username/surforecast`  
2. Enable GitHub Pages on `main` branch, `/docs` folder  
3. Local repo pushes to GitHub; GitHub Pages serves from `/docs`  
4. Cron job runs script, updates `docs/index.html`, commits, pushes  

### 7.4 Maintenance & Operations  
- **Daily**: Automatic run at 05:45 LT via cron  
- **Weekly**: Check logs for any errors  
- **Monthly**: Verify data sources still accessible  
- **As Needed**: Update beach definitions, rating formulas, or wetsuit guidelines  

---  

## 8. Future Enhancements  

| Idea | Benefit |
|------|---------|
| **Interactive Elements** | Add tide charts or swell graphs using JavaScript libraries |
| **Multiple Locations** | Expand to other Australian coastal regions |
| **User Preferences** | Allow users to save preferred beaches via localStorage |
| **Multi-language Support** | Add i18n for international visitors |
| **API Caching** | Reduce API calls by caching responses for short periods |
| **Docker Container** | Package script for easy deployment on any system |
| **Email Newsletter Option** | Optional daily email delivery alongside web version |

---  

*This specification transforms the original Telegram-based surf report concept into a static webpage solution that leverages GitHub Pages for reliable, zero-maintenance hosting while maintaining all core surf reporting functionality.*