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
| **FR-5** | **Surf Rating** – Calculate 0‑5 star rating per beach using two-stage formula: (1) wave height score = min(5, 5 × (effective_height / 1.83)^0.85) capped at 1.83m (6 ft / overhead); (2) multiplicative quality factor = wind_quality × attack_factor × tide_factor. Final rating = wave_height_score × wave_quality, rounded to nearest 0.5★. | Rating matches specification in Section 4.3. |
| **FR-6** | **Board Recommendation** – Map effective height to board types (see Section 4.5) with adjustments for short period (< 8s → more volume), long period (≥ 12s + ≥ 1.2m → favour step-up), and poor wave quality (reduces effective height for board selection → more volume). | Recommendation string follows rule set; examples: 0.4m → Longboard/Funboard, 0.9m → Groveller/Fish/Funboard, 1.7m → Shortboard/Mid-Length/Step-Up, 3.0m → Step-Up. |
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
| Long Reef | 158° | 68° | 22° | Northernmost beach. Wide exposure from E (90°) to S (180°). |
| Dee Why | 135° | 67.5° | 22.5° | Southeast facing, wide left exposure, tightly shadowed right. |
| Curl Curl | 112° | 44.5° | 45.5° | East-southeast, nearly symmetrical ENE to SSE. |
| Freshwater | 135° | 35° | 22.5° | Southeast facing, moderate left, tight right shadow. |
| North Steyne | 90° | 45° | 45° | Eastern end of Manly, symmetrical NE to SE. |
| South Steyne | 68° | 45.5° | 22° | East-northeast, wide left, tight right. Loses south swells quickly. |

### 4.3 Surf Rating Formula  

The rating is computed per-beach in two stages:

1. **Wave Height Score** (0–5):  
   `wave_height_score = min(5, 5 × (effective_height / 1.83)^0.85)`  
   - Capped at **1.83m (6 ft / overhead)**, which scores 5★.  
   - Beyond 1.83m, height plateaus — quality factors differentiate bigger waves.  
   - Wave period is already baked into `effective_height` via shoaling amplification.  

2. **Wave Quality Factor** (0–1, multiplicative):  
   `wave_quality = wind_quality × attack_factor × tide_factor × embayment_factor`  
   - **Wind quality**: blend of direction (offshore → onshore) and speed, from 0.15 (gale onshore) to 1.0 (light offshore breeze)  
   - **Attack factor**: angle of swell relative to beach face — 1.0 for 15°–45° (perfect peeler), drops to 0.5 for close-out or extreme angle  
   - **Tide factor**: 1.0 for 0.5–1.5m range, linearly decreasing to 0.7 at 0m or 3.0m — narrowed from 0.6 floor since tide alone rarely ruins a session  
   - **Embayment factor**: how open or closed the beach is relative to the size of the swell. Wide-open beaches (Long Reef, Curl Curl) score near 1.0 on small-to-moderate days. Narrow/closed beaches (Freshwater) drop to ~0.5 on big groundswell days due to close-out risk.  

**Final Rating** = `wave_height_score × (2 + wave_quality) / 3`  
Wave height carries twice the weight of quality. Rounded to nearest 0.5★, displayed as ★★★★☆ (full stars + optional ½).  

**Key property**: The product is strict — one bad factor (e.g., onshore gale at 0.15) heavily penalises the score regardless of height.  

### 4.4 Wetsuit Guide  

Real-time SST from IMOS RAMSSA L4 satellite analysis, queried daily via S3, with temperature-based thresholds:
- ≥ 22°C → Boardshorts or rash vest  
- 20–21°C → Spring suit (2 mm)  
- 17–19°C → 3/2 steamer  
- 14–16°C → 4/3 steamer  
- < 14°C → 5/4 steamer with booties, gloves, hood  

Falls back to monthly climatology if satellite data is unavailable.

### 4.5 Board Recommendation Guide  

| Face Height | Feet | Boards |
|-------------|------|--------|
| < 0.3m | < 1 ft | Longboard, Log |
| 0.3–0.6m | 1–2 ft | Longboard, Funboard |
| 0.6–1.0m | 2–3 ft | Groveller, Fish, Funboard |
| 1.0–1.5m | 3–5 ft | Shortboard, Fish, Mid-Length |
| 1.5–2.0m | 5–7 ft | Shortboard, Mid-Length, Step-Up |
| 2.0–2.5m | 7–8 ft | Shortboard, Step-Up |
| > 2.5m | > 8 ft | Step-Up |

**Period adjustments:**
- < 8s (windswell) → bump up one volume category
- ≥ 12s + ≥ 1.2m (powerful groundswell) → favour Step-Up

**Quality adjustment:**
`adj_height = effective_height × (0.7 + wave_quality × 0.3)`  
Poor quality = lower adj_height = more volume recommended.

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
| **Embayment Factor** – Wave quality factor based on beach openness (L/R window) vs swell size. Wide beaches (Long Reef) handle big swells; narrow beaches (Freshwater) close out. | Physically realistic quality penalty for enclosed beaches on big days. | ✅ **Implemented** |
| **Surf‑Quality Index** – Combine wave power, period, and wind into a single numeric score. | Simplifies decision making. | ⬜ Planned |
| **Rich Media Attachments** – Include a small tide‑graph or wave‑direction rose as an image attachment. | Visual enhancement. | ⬜ Planned |
| **User‑Configurable Beaches** – Allow per‑user beach list via the existing JSON config mechanism. | Personalisation without code change. | ⬜ Planned |
| **Unit‑Test Suite** – Add `pytest` tests for each function with CI integration. | Higher confidence in changes. | ⬜ Planned |
| **Dockerised Version** – Package script & dependencies for easy deployment on other hosts. | Portability. | ⬜ Planned |

---  

*End of Specification*