# Product Specification – Northern Beaches Surf Check Static Webpage

**Version:** 2.0  
**Date:** 2026-06-28  
**Author:** Updated from Hermes Agent spec for static webpage deployment  

---  

## 1. Overview  

Northern Beaches Surf Check is a static webpage that provides daily surf reports for Sydney's Northern Beaches. The system runs automatically each morning, fetches live marine and meteorological data, processes it into a surf report, and publishes a static HTML page to GitHub Pages. The system runs via a local cron job that runs the generation script and commits/pushes the page to trigger GitHub Pages publishing.  

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
| **FR-4** | **Beach-Specific Wave Height** – For each beach (Long Reef, Dee Why, Curl Curl, Freshwater, North Steyne, South Steyne), compute effective height using a direct swell window (primary aspect ± left/right offset, default 10°). Swell inside the window is fully exposed. Outside the window, height is reduced by Wiegel diffraction coefficients (K<sub>d</sub> = 0.70 at 10° past window edge, falling to 0.15 at 90° past). The breaker formula is then applied to estimate breaking height. | Effective height ≥ 0 and ≤ offshore height; exposure % follows Wiegel K<sub>d</sub> curve × 100. |
| **FR-5** | **Surf Rating** – Calculate 0‑5 star rating based on effective wave height (scaled to 2m max) and wave period (scaled 6‑15s), multiplied by tide factor (optimal tide 0.5‑1.5m → 1.0; outside range reduces linearly). | Rating matches specification table (see Section 4.1). |
| **FR-6** | **Board Recommendation** – Map effective height to board type (Log < 0.5m, Funboard 0.5‑1.0m, Shortboard 1.0‑2.0m, Gun > 2.0m) with dual‑option handling when height within 0.1m of threshold; adjust down one step if period < 8s. | Recommendation string follows rule set; examples: 0.45m → Log, 0.95m → Funboard/Shortboard, 2.2m → Gun. |
| **FR-7** | **Wetsuit Recommendation** – Based on month‑derived sea‑surface temperature (see Table 1) and Quiksilver guide, output textual recommendation (e.g., “Boardshorts or rash vest”, “Spring suit (2mm)”, “3/2 full wetsuit”, “4/3 full wetsuit with booties, gloves, hood”). | Recommendation matches decision table for given month. |
| **FR-8** | **Report Generation** – Produce a static HTML surf report with sections: header, offshore swell, wind, per‑beach cards (beach [aspect° (dir)] Surf: X.Xm [Ys @ Z%] ★★☆☆☆ Board: A/B), overall summary, max expected tide, water temp & wetsuit recommendation, timestamp. | Generated HTML matches template in Section 5 and is valid HTML5. |
| **FR-9** | **Automated Deployment** – Local cron job runs generation script daily at 05:45 LT, commits updated HTML to git repo, and pushes to origin to trigger GitHub Pages rebuild. | Job runs successfully each morning; GitHub Pages updates within minutes of push; commit history shows daily updates. |
| **FR-10** | **Logging & Error Handling** – Script logs operations and errors to local log file; on critical failures, generates error HTML page indicating issue. | Logs contain timestamps and error details; fallback error page is valid HTML. |

---  

## 4. Data Sources & Calculations  

### 4.1 Data Sources  
- **Beach Configuration**: `beaches.json` in the project root — defines primary aspect, left/right offsets, and notes for each beach.  
- **Open-Meteo Marine API**: https://marine-api.open-meteo.com/v1/marine  
  Parameters: latitude=-33.78, longitude=151.30, hourly=wave_height,wave_period,wave_direction,wind_speed,wind_direction  
- **Open-Meteo Weather API**: https://api.open-meteo.com/v1/forecast  
  Parameters: latitude=-33.78, longitude=151.30, hourly=temperature_2m,weathercode  
- **IMOS S3 Bucket (RAMSSA L4 SST)**: s3://imos-data/IMOS/SRS/SST/ghrsst/L4/RAMSSA/  
  Real-time sea surface temperature from satellite analysis, queried daily via `aws s3 cp --no-sign-request`.  
  Public bucket, no credentials required. Falls back to monthly climatology on error.
- **Manly Hydraulics Laboratory (MHL) API**: https://mhl.nsw.gov.au/Data/SeaLevel/Data/TimeSeries/213470.csv  
  Returns CSV with timestamp and sea level values  
  *(Currently unavailable; uses harmonic tide model as fallback)*  

### 4.2 Beach Definitions  

| Beach | Aspect (°) | Left offset | Right offset | Notes |
|-------|-----------|-------------|--------------|-------|
| Long Reef | 158° | 10° | 10° | Northernmost beach, southeast-southeast exposure |
| Dee Why | 135° | 10° | 10° | Southeast facing beach, sheltered by southern headland |
| Curl Curl | 112° | 10° | 10° | East-southeast exposed beach with consistent swell |
| Freshwater | 135° | 10° | 10° | Southeast facing beach, protected by northern headland |
| North Steyne | 90° | 10° | 10° | Eastern end of Manly Beach, exposed to east swells |
| South Steyne | 68° | 10° | 10° | East-northeast end of Manly Beach, NE swell exposure |

### 4.3 Surf Rating Formula  

The rating combines three normalized factors:  
1. **Wave Height Factor**: min(effective_height / 2.0, 1.0)  
2. **Period Factor**: min((wave_period - 6) / (15 - 6), 1.0) clamped to [0,1]  
3. **Tide Factor**:  
   - If 0.5 ≤ tide_height ≤ 1.5: factor = 1.0  
   - If tide_height < 0.5: factor = tide_height / 0.5  
   - If tide_height > 1.5: max(0, (3.0 - tide_height) / 1.5)  

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

*Note: Monthly table is the fallback only. Real-time SST from IMOS RAMSSA L4 is queried daily via S3 and used preferentially, with temperature-based thresholds (≥22°C rash vest, 20–21°C spring suit, 17–19°C 3/2, 14–16°C 4/3, <14°C 5/4+hood).*

---  

## 5. Report Template (HTML Structure)  

The generated HTML (`docs/index.html`) is a full-page, standalone document with embedded CSS and JavaScript. See the live site or `docs/index.html` in the repository for the current structure. Key sections:

- **Header**: Title, timeframe navigation buttons (6–9am / 9–12pm / 12–3pm / 3–6pm), and generation timestamp (in footer)
- **Best Beaches**: Top 3 beaches by composite score (rating × wind × tide)
- **Overall Conditions**: Swell, wind, tide, water temperature
- **Beach Cards**: Per-beach grid showing wave height, period, exposure, wind condition, star rating, board recommendation
- **Footer**: Generation timestamp, data source links
- **JavaScript**: Client-side timeframe toggling with localStorage persistence
- **CSS Tooltips**: Floating info boxes on hover for data source attribution

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

| Idea | Benefit | Status |
|------|---------|--------|
| **Dynamic Water Temperature** – Pull real‑time SST from IMOS S3 bucket (RAMSSA L4) instead of month‑lookup. | More precise wetsuit advice. | ✅ **Implemented** |
| **Per-beach swell exposure windows** – L/R offsets defining direct swell window; Wiegel diffraction curves for headland shadowing. | Physically realistic wave reduction past headlands. | ✅ **Implemented** |
| **Beach config in JSON** – `beaches.json` with aspect, offsets, notes. | Easy to tune without touching code. | ✅ **Implemented** |
| **Multiple Forecast Horizons** – Offer 12‑hour and 24‑hour outlooks. | Better planning for later sessions. | ⬜ Planned |
| **Surf‑Quality Index** – Combine wave power, period, and wind into a single numeric score. | Simplifies decision making. | ⬜ Planned |
| **Rich Media Attachments** – Include a small tide‑graph or wave‑direction rose as an image attachment. | Visual enhancement. | ⬜ Planned |
| **User‑Configurable Beaches** – Allow per‑user beach list via the existing JSON config mechanism. | Personalisation without code change. | ⬜ Planned |
| **Unit‑Test Suite** – Add `pytest` tests for each function with CI integration. | Higher confidence in changes. | ⬜ Planned |
| **Dockerised Version** – Package script & dependencies for easy deployment on other hosts. | Portability. | ⬜ Planned |

---  

*End of Specification*