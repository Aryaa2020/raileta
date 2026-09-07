# RailETA Controller Dashboard

Operations view for section controllers, aligned to the SIH proposal.

## Included

- Corridor track with train placement from accepted station events.
- On-time, attention, and late counts.
- Selected-train progress derived from the last reported station.
- Next-stop ETA, 80% calibrated window, delay factors, source freshness, and fallback source.
- Event-feed refresh every 30 seconds.

The dashboard does not imply live GPS navigation or execute dispatch decisions. Run it with the Django API on port 8000.
