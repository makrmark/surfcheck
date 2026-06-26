# Surforecast - Automated Surf Report for GitHub Pages

A automated surf report system that generates daily surf reports for Sydney beaches and publishes them as a static webpage using GitHub Pages.

## Overview

Surforecast fetches live marine and meteorological data from Open-Meteo APIs and tide observations from Manly Hydraulics Laboratory (MHL), processes it into a comprehensive surf report, and publishes it as a static HTML page. The system runs automatically each morning via a local scheduler (launch agent on macOS) and commits the updated page to trigger GitHub Pages deployment.

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
- git
- macOS (for launch agent setup) or Linux (for cron)

### Setup

1. **Clone or download this repository**

2. **Install required Python packages**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
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
   - Push initial commit:
     ```bash
     git add .
     git commit -m "Initial commit"
     git push -u origin main
     ```

5. **Set up automation**:
   
   **macOS (using launch agent)**:
   ```bash
   # Copy the plist file to ~/Library/LaunchAgents/
   cp surforecast.plist ~/Library/LaunchAgents/
   
   # Load the agent
   launchctl load ~/Library/LaunchAgents/surforecast.plist
   
   # To start immediately:
   launchctl start com.user.surforecast
   
   # To check status:
   launchctl list | grep surforecast
   ```
   
   **Linux (using cron)**:
   ```bash
   # Edit crontab
   crontab -e
   
   # Add this line to run daily at 5:45 AM
   45 5 * * * cd /path/to/surforecast && ./venv/bin/python surf_report.py >> surforecast.log 2>&1
   ```

## How It Works

1. **Data Collection**: The Python script fetches data from:
   - Open-Meteo marine endpoint for wave conditions
   - Open-Meteo forecast endpoint for wind conditions  
   - MHL CSV endpoint for tide observations (with harmonic model fallback)

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
├── surforecast.plist       # macOS launch agent configuration
├── .gitignore              # Git ignore rules
├── README.md               # This file
├── venv/                   # Python virtual environment
├── docs/                   # GitHub Pages source (served live)
│   └── index.html          # Generated surf report
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
- **macOS**: Edit the `StartCalendarInterval` in `surforecast.plist`
- **Linux**: Modify the cron job time
- The script itself uses report time of 6:00 AM for calculations

## Maintenance

### Logs
- Check terminal output when running manually
- Review `~/Library/Logs/com.apple.launchd.peruser.*/com.user.surforecast.out.err` (macOS)
- GitHub commit history shows deployment timeline
- GitHub Pages build logs available in repository settings

### Troubleshooting
1. **No updates on GitHub Pages**:
   - Verify launch agent/cron is running: `launchctl list | grep surforecast` (macOS) or check cron logs
   - Test manual execution: `./venv/bin/python surf_report.py`
   - Verify git push works: `git add . && git commit -m "Test" && git push`

2. **Stale data**:
   - Check API status: Open-Meteo and MHL services
   - Review generated `docs/index.html` for error messages
   - Verify script has internet access

3. **Permission issues**:
   - Ensure script has write access to `docs/` directory
   - Verify git has access to push to remote repository
   - For launch agent, check StandardOutPath and StandardErrorPath for logs

## License

MIT License - feel free to modify and use for your own surf reporting needs!

## Acknowledgments

- Data provided by [Open-Meteo](https://open-meteo.com/)
- Tide data from [Manly Hydraulics Laboratory (MHL)](https://mhl.nsw.gov.au/)
- Inspired by traditional surf reporting services