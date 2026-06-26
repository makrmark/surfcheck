# Surforecast - Automated Surf Report for GitHub Pages

A automated surf report system that generates daily surf reports for Sydney beaches and publishes them as a static webpage using GitHub Pages.

## Overview

Surforecast fetches live marine and meteorological data from Open-Meteo APIs and tide observations from Manly Hydraulics Laboratory (MHL), processes it into a comprehensive surf report, and publishes it as a static HTML page. The system runs automatically each morning via a local scheduler and commits the updated page to trigger GitHub Pages deployment.

## Features

- 🌊 Fetches real-time wave height, period, and direction data
- 💨 Retrieves current wind conditions
- 🌊 Gets tide observations from MHL with harmonic model fallback
- 🏖️ Calculates beach-specific conditions for Collaroy, Freshwater, and Manly
- ⭐ Generates surf ratings based on wave height, period, and tide conditions
- 🏄 Provides board and wetsuit recommendations
- 📱 Responsive HTML design that works on mobile and desktop
- 🔄 Automatic daily updates via local scheduler
- ⚡ GitHub Pages deployment via git push

## Data Sources

- **Open-Meteo Marine API**: Wave height, period, direction, wind speed/direction
- **Manly Hydraulics Laboratory (MHL)**: Real-time tide observations from Station 213470
- **Internal Models**: Harmonic tide model fallback, surf rating algorithm, wetsuit guide

## Installation

### Prerequisites

- Python 3.7+
- pip (Python package manager)
- git
- Access to cron (Linux/macOS) or Task Scheduler (Windows)

### Setup

1. **Clone or download this repository**

2. **Install required Python packages**:
   ```bash
   pip install requests
   ```

3. **Configure git repository**:
   ```bash
   git init
   git remote add origin https://github.com/your-username/surforecast.git
   git branch -M main
   ```

4. **Create GitHub repository**:
   - Go to GitHub and create a new repository named `surforecast`
   - Enable GitHub Pages in repository settings:
     - Source: `main` branch
     - Folder: `/docs` (root)
   - Note: The script will automatically push to the `docs` folder

5. **Set up automation**:
   - **macOS/Linux (cron)**:
     ```bash
     # Edit crontab
     crontab -e
     
     # Add this line to run daily at 5:45 AM
     45 5 * * * cd /path/to/surforecast && /usr/bin/python3 surf_report.py >> surforecast.log 2>&1
     ```
   
   - **Alternative (launch agent on macOS)**:
     See `surforecast.plist` example below

## How It Works

1. **Data Collection**: The Python script fetches data from:
   - Open-Meteo marine endpoint for wave conditions
   - Open-Meteo forecast endpoint for wind conditions  
   - MHL CSV endpoint for tide observations

2. **Processing**: 
   - Calculates tide heights using observed data anchored to harmonic model
   - Computes beach-specific effective wave heights considering beach aspect
   - Generates surf ratings (0-5 stars) based on height, period, and tide
   - Provides board and wetsuit recommendations

3. **Report Generation**: Creates a responsive HTML report with:
   - Current offshore conditions
   - Individual beach cards with ratings and recommendations
   - Overall summary with tide and water temperature info
   - Timestamp and data source attribution

4. **Deployment**: 
   - Saves report to `docs/index.html`
   - Commits changes to git
   - Pushes to origin remote
   - GitHub Pages automatically rebuilds and serves the updated page

## File Structure

```
surforecast/
├── surf_report.py          # Main report generation script
├── docs/                   # GitHub Pages source (served live)
│   └── index.html          # Generated surf report
├── README.md               # This file
└── .git/                   # Git repository data
```

## Customization

### Modifying Beaches
Edit the `BEACHES` dictionary in `sur_report.py`:
```python
BEACHES = {
    "Your Beach Name": degrees_from_north,  # 0=N, 90=E, 180=S, 270=W
    # Add more beaches as needed
}
```

### Adjusting Rating Algorithm
Modify the `calculate_surf_rating()` and `tide_factor()` functions in `sur_report.py`.

### Changing Update Time
Modify the cron job time or launch agent schedule. The script itself uses report time of 6:00 AM for calculations.

## Maintenance

### Logs
- Check `surforecast.log` for execution logs
- GitHub commit history shows deployment timeline
- Review GitHub Pages build logs if deployment fails

### Troubleshooting
1. **No updates on GitHub Pages**: 
   - Check if cron job is running: `grep CRON /var/log/syslog` (Linux) or check Mail.app (macOS)
   - Verify git push is working: try manual run `python3 surf_report.py && git add . && git commit -m "Update" && git push`

2. **Stale data**:
   - Check API status: Open-Meteo and MHL services
   - Review error reports in `docs/index.html` if generation fails

3. **Permission issues**:
   - Ensure script has write access to `docs/` directory
   - Verify git has access to push to remote repository

## License

MIT License - feel free to modify and use for your own surf reporting needs!

## Acknowledgments

- Data provided by [Open-Meteo](https://open-meteo.com/)
- Tide data from [Manly Hydraulics Laboratory (MHL)](https://mhl.nsw.gov.au/)
- Inspired by traditional surf reporting services