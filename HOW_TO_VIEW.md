# How to view RailETA

## Start the submission-aligned stack

From `F:\sah\raileta`:

```powershell
.\START_ALL.ps1
```

Or start the API and UIs individually:

```powershell
.\start_backend.ps1
.\start_passenger_ui.ps1
.\start_station_display.ps1
.\start_controller_dashboard.ps1
```

The API is available at `http://localhost:8000`.

## Demo flow

1. Run `python manage.py seed_demo` once after migrations.
2. Passenger UI: search `12007`, `12639`, or `22625` to view MAS-SBC station-event progress, the 80% calibrated arrival window, and reason codes.
3. Controller dashboard: select a train on the Chennai Central (MAS) → KSR Bengaluru (SBC) corridor track to view event-derived progress, next-stop ETA, freshness, and fallback source.
4. Station display: use `1`, `2`, or `3` to switch between Chennai Central, Katpadi, and KSR Bengaluru; press `R` to refresh.

The dashboards do not present GPS navigation or executable dispatch decisions. When configured public feeds are unavailable, the seeded fixture data keeps the demonstration repeatable.
