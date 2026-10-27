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
- [x] Preserve nested route headings and combine separate service tables only when they share a selected direction and Service 1/2/3 structure
- [x] Next departure, minutes-until, and full-departures sensors
- [x] Unit tests for both known Route 188 stop rows and duplicate-stop selection
- [x] GitHub Actions parser test workflow
- [ ] Verify live Route 188 page structure and both directions
- [x] Add representative parser tests for Route 177 grouped weekday/holiday columns, Route 189 weekday/holiday columns, Route 192 simple Times tables, and Route 195 outbound/return layouts
- [ ] Validate extracted times against every live route page before claiming broad route compatibility
- [x] Allow the configured timetable to be limited to selected days of the week
- [x] Allow an optional service-column heading to select one timetable column
- [x] Support repeated grouped service headings such as Route 188 journey groups
- [x] Automatically build ordinary weekday schedules from explicitly labelled service columns when no manual service-column override is set
- [x] Support an explicitly selected public-holiday timetable column and optional Home Assistant calendar date overrides
- [ ] Verify holiday-calendar service compatibility on a live Home Assistant instance
- [x] Discover route URLs from the published Local Link timetable index during setup\n- [ ] Discover stop names from the selected route page so users do not have to type a stop name
- [ ] Review error handling, diagnostics, and HACS release readiness

## Development installation

The integration is not yet a stable HACS release.

1. Copy `custom_components/local_link_timetables` into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration**.
4. Search for **Local Link Timetables**.
5. Choose a route, then select a discovered stop (or type it manually if discovery is unavailable), an optional direction/section text, an optional service-column heading (for example `Mon–Fri`), the days this configured timetable operates, and a friendly name.

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

- The parser supports selecting departure-time cells by service-column heading, including repeated grouped headings such as Route 188 and the different outbound/return column layouts represented by Routes 189 and 195. For simple tables such as LH701, nested direction headings are retained and multiple Service 1/2/3 tables are combined only when a matching direction is explicitly selected. Route 177, 188, 189, 192, 195, and LH701 now have representative layout fixtures. These are fixture-based parser tests, not a guarantee that every live route page is compatible; verify the actual departures for the selected stop and direction.
- If the same stop appears in multiple rows with different times, setup now fails safely and asks for a direction/section hint. The direction hint can match the stop row or its section heading. The optional service-column hint should match the published header text exactly enough to identify the intended column; if a route has grouped or unusual headers, verify the extracted departures before relying on them.
- Route selection is discovered from the published timetable index, but stop selection is still manual. The index is fetched during setup; if unavailable, the form falls back to a manual URL field.\n- Service days are currently selected manually for one configured list of departure times. When the service-column field is left blank, the integration now combines columns whose published weekday headings apply to each ordinary weekday (for example, Route 188's Mon–Sat journey group plus its Monday–Sunday group). A manual service-column heading still overrides this behaviour. Public-holiday overrides are optional and must be configured explicitly: select a separate column whose heading mentions public holidays, select a dedicated calendar containing only public holidays, and select the ordinary service column as well. The integration checks calendar events over the next 15 days during its normal refresh. If the calendar service is unavailable, it logs a warning and continues with ordinary schedule logic; holiday departures may then be missed. Calendar behaviour still requires live Home Assistant verification. Do not use a general family/events calendar, because every event date in the selected calendar is treated as a public holiday.
- Timetable data may change on the provider's website. Check the published timetable before travelling.

## Tests

Parser tests use Python's standard `unittest` runner and do not require a Home Assistant installation:

```bash
python -m unittest discover -s tests -v
```

## HACS

HACS release metadata is included, but the project should not be treated as production-ready or added to the default HACS store until the remaining route compatibility and service-day tests are complete.
