# TODO — Northern Beaches Surf Check

Known deficiencies, planned enhancements, and ideas for future work.

---

## Known Deficiencies

### Headland diffraction model uses idealised geometry
The Wiegel diffraction curves assume a simplified semi-infinite breakwater. Real headlands have irregular shapes, cliffs, and varying distances to the beach. The default 10° L/R window is a reasonable starting point but should ideally be calibrated per beach using local knowledge or wave modelling.

### No consideration of bathymetric refraction inside the shadow zone
Diffracted waves may refract as they approach the beach, bending back towards the headland or spreading along the coast. The current model assumes diffracted waves continue straight after the headland.

### Breaker index / shoal factor ignores beach slope
The breaker index literature (Coastal Wiki, MDPI) shows that the wave height at breaking depends significantly on the shoreface slope. Our `shoal_factor(period)` is a uniform curve applied to all beaches. In reality, steeper beaches (e.g. South Steyne) amplify waves differently than gentle slopes (e.g. Long Reef). The existing empirical formulas use `γb = f(H₀/L₀, β)` where β is the beach slope.

### Diffraction coefficient does not vary with wave period
The Coastal Engineering Manual notes that shorter wavelengths (higher-frequency waves) undergo greater height reduction for a given shadow angle because `r/L` is larger. Our `_diffraction_coefficient()` returns the same Kd for a 6s windswell and a 16s groundswell at the same shadow angle. In reality, longer-period swell wraps around headlands more effectively.

### Harmonic tide model limited to M2 + S2
The tide model uses only the two largest constituents (M2 lunar, S2 solar). The Australian Hydrographic Office provides **22 harmonic constituents** for Sydney Harbour (Fort Denison) on request. Missing constituents (N2, K1, O1, etc.) introduce errors of up to ±0.2m, especially during neap tides or when meteorological effects (wind setup, barometric pressure) are present.

### Wiegel Kd interpolation uses only 5 curve points
The diffraction table is interpolated from just 5 (shadow_angle, Kd) pairs. The Coastal Engineering Manual references Wiegel (1962) which tabulates values at 15° intervals across multiple approach angles. A denser interpolation table would improve accuracy, particularly in the 0–30° range where the curve is steepest.

### All beaches use the same L/R offsets
Per-beach offsets are defined in `beaches.json` but have never been calibrated against real observations. Headland distances, cliff heights, and offshore bathymetry vary significantly along the Northern Beaches coastline.

### Single offshore data point for all beaches
Marine and wind forecasts are retrieved for a single coordinate offshore of Sydney (-33.78, 151.30). In reality:
- Northern beaches (Long Reef, Dee Why) experience slightly different offshore conditions than southern beaches (South Steyne).
- Wind data is measured at 10m above the ocean surface at a single point; local wind effects (terrain channelling, sea-breeze gradients) are not captured.

### No tide graph
The report shows the current tide height and trend as text, but there is no visual tide graph showing the full daily curve. A small SVG or canvas chart would give surfers a quick read on when the tide will be favourable.

### Board recommendations are static rules
Board type mapping is based on generic height and period thresholds. It does not incorporate local knowledge (e.g. "Dee Why handles bigger surf better than Curl Curl due to the deeper channel") or user preference.

### Wetsuit recommendation uses coastal SST, not beach-specific
The IMOS RAMSSA L4 satellite product provides a single SST value for the Northern Beaches coastal edge. In practice, there can be 1–2°C variation between beaches due to freshwater runoff (e.g. Narrabeen Lagoon outlet) or upwelling.

### IMOS SST requires AWS CLI
The real-time SST pipeline depends on `aws s3 cp --no-sign-request` being available on the host. This is an additional system dependency beyond Python packages.

---

## Planned Enhancements

- [x] **Per-beach swell exposure windows** — Beach config in `beaches.json` with L/R offsets; Wiegel diffraction curves for headland shadowing beyond the window.
- [ ] **Extend tide model to 22 harmonic constituents** — AHO provides full constituent set for Fort Denison on request. Would improve accuracy at neap tides and under meteorological effects.
- [x] **Embayment factor** — Wave quality multiplier based on beach openness (angular window between headlands) vs wave energy demand. Wide beaches (Long Reef, Curl Curl) score high; narrow beaches (Freshwater) get penalised on big-swell days. Mapped via piecewise curve from the W/Lb ratio theory. Displayed as a new "Embay." column on each beach card.
- [ ] **Period-dependent diffraction** — Kd should vary with wave period (shorter waves diffract less). Implement `Kd = f(shadow_angle, r/L)` per Coastal Engineering Manual.
- [ ] **Beach-specific shoal factors** — Replace uniform `shoal_factor(period)` with per-beach curves accounting for shoreface slope (steeper = more amplification).
- [ ] **Calibrate L/R offsets per beach** — Current offsets are qualitative estimates. Cross-reference against real surf reports or wave buoys to validate.
- [ ] **Tide graph** — Add an inline SVG tide curve for the day, generated from the harmonic model.
- [ ] **Rain / air temperature display** — Include hourly precipitation probability and air temp from the Open-Meteo weather API in the Overall Conditions section.
- [ ] **Wind gust data** — Add gust speed to the wind display (Open-Meteo provides `windgusts`).
- [ ] **Multiple forecast days** — Add a day-selector alongside the timeframe selector for tomorrow and the day after.
- [ ] **Unit test suite** — Add `pytest` tests with mocked API responses for all calculation functions.
- [ ] **Dockerised deployment** — Package with Docker for easier setup on any host.
- [ ] **User-configurable beaches** — Allow a JSON config file to define custom beach lists, aspects, and notes.

---

## Nice-to-Haves

- UV index and sun protection提醒 for long sessions.
- Surf-cam thumbnails (if publicly available APIs exist for Northern Beaches).
- PDF/print-friendly report layout.
- Email or SMS alert when conditions exceed a quality threshold at a favourite beach.
- Historical report archive (by date) so users can look up past conditions.

---

*Generated: 2026-06-28*
