# TODO — Northern Beaches Surf Check

Known deficiencies, planned enhancements, and ideas for future work.

---

## Known Deficiencies

### Wave model based only on beach aspect, not actual exposure
The wave height calculation for each beach uses a simple cosine falloff based on the difference between offshore wave direction and beach aspect. This does not account for:

- **Headland shadowing** — e.g. Freshwater is partially sheltered by the northern headland at North Head, reducing effective swell energy from certain directions regardless of aspect.
- **Local bathymetry** — offshore reefs, sandbars, and depth contours refract and focus wave energy in ways the simple model ignores.
- **Sheltered vs exposed ends** — within a single beach (e.g. North Steyne vs South Steyne), the actual swell exposure varies due to the shape of the coastline.

A more accurate model would use a per-beach exposure window (e.g. "receives swell from 60°–120° with peak at 90°") rather than a single aspect figure.

### Harmonic tide model limited to M2 + S2
The tide model uses only the two largest constituents (M2 lunar, S2 solar). Missing constituents (N2, K1, O1, etc.) introduce errors of up to ±0.2m, especially during neap tides or when meteorological effects (wind setup, barometric pressure) are present.

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

- [ ] **Per-beach swell exposure windows** — Replace single-aspect model with per-beach directional windows that account for headland sheltering and local bathymetry.
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
