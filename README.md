# Local Link Timetables for Home Assistant

A HACS custom integration for reading published Local Link timetable pages and exposing departure times as Home Assistant sensors.

> **Early development / experimental.** Route 188 is the first validation target. Do not rely on this integration for time-critical travel until multiple routes, directions, and service-day variations have been tested.

This is an independent community project and is not affiliated with or endorsed by Local Link. It reads published timetable pages; it does not provide live vehicle tracking.

## Current development status

- [x] Initial Home Assistant integration structure
- [x] UI setup flow for a timetable URL, stop name, and optional direction/section hint
- [x] Parser for adjacent timetable times such as `06:5708:23`
- [x] Reject ambiguous duplicate-stop rows instead of silently choosing the row with the most times
- [x] Prefer exact stop-cell matches and use word-boundary matching to avoid similarly named stops
- [x] Next departure, minutes-until, and full-departures sensors
- [x] Unit tests for both known Route 188 stop rows and duplicate-stop selection
- [x] GitHub Actions parser test workflow
- [ ] Verify live Route 188 page structure and both directions
- [x] Add representative parser tests for Route 189 weekday/holiday columns and Route 195 outbound/return layouts
- [ ] Validate extracted times against every live route page before claiming broad route compatibility
- [x] Allow the configured timetable to be limited to selected days of the week
- [x] Allow an optional service-column heading to select one timetable column
- [x] Support repeated grouped service headings such as Route 188 journey groups
- [ ] Automatically choose the correct weekday/weekend/public-holiday column for the current date
- [ ] Add route/stop discovery so users do not have to type a stop name
- [ ] Review error handling, diagnostics, and HACS release readiness

## Development installation

The integration is not yet a stable HACS release.

1. Copy `custom_components/local_link_timetables` into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration**.
4. Search for **Local Link Timetables**.
5. Enter the timetable page URL, stop name as printed on the page, an optional direction/section text, an optional exact service-column heading (for example `Mon–Fri`), the days this configured timetable operates, and a friendly name.

For initial validation, use the Route 188 page:

`https://locallinklmf.ie/tfi-route-188/`

Example stop names from known timetable rows are `Kentstown Church`, `Kennedy Road`, `Enfield`, `Ashbourne`, and `Balbriggan Station`.

## Sensors

Each configured stop creates:

- **Next departure** — the next listed time.
- **Minutes until departure** — countdown in minutes, refreshed each minute without fetching the webpage every minute.
- **Departures** — comma-separated times, with the full list also available as an attribute.

The source timetable is fetched every 15 minutes. A failed fetch or parse is reported through Home Assistant's coordinator status and logs.

## Important limitations

- The parser supports selecting departure-time cells by service-column heading, including repeated grouped headings such as Route 188 and the different outbound/return column layouts represented by Routes 189 and 195. These are fixture-based parser tests, not a guarantee that every live route page is compatible; verify the actual departures for the selected stop and direction.
- If the same stop appears in multiple rows with different times, setup now fails safely and asks for a direction/section hint. The direction hint can match the stop row or its section heading. The optional service-column hint should match the published header text exactly enough to identify the intended column; if a route has grouped or unusual headers, verify the extracted departures before relying on them.
- Service days are currently selected manually for one configured list of departure times. The optional service-column field can select a named column such as “Mon–Fri” or “Mon–Sun & Public Holidays”, but the integration does not yet automatically switch columns based on today's weekday or public holidays. Configure one service pattern per entry and do not treat this as automatic public-holiday support.
- Timetable data may change on the provider's website. Check the published timetable before travelling.

## Tests

Parser tests use Python's standard `unittest` runner and do not require a Home Assistant installation:

```bash
python -m unittest discover -s tests -v
```

## HACS

HACS release metadata is included, but the project should not be treated as production-ready or added to the default HACS store until the remaining route compatibility and service-day tests are complete.
