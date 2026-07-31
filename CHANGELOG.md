# Changelog

## Unreleased

* Norwegian bird names are bundled from the Norwegian Bird Names Committee's
  AviList workbook and can be refreshed with the localization importer.
* Added selectable illustration/sketch packs, paginated activity logs, and the
  stable current-display API.
* Wired the display policy settings: detections below the confidence
  threshold no longer change artwork, and per-species duplicate cooldown
  coalesces repeat sightings into a single render.
* Implemented automatic TV wake (Wake-on-LAN via the TV MAC address) and quiet
  hours for the TV sync worker; Settings gained a Display & TV section with
  display mode, collage window, update cadence, wake, and quiet-hour controls.
* Added retention cleanup: one composition (file and record) per day for the
  past year and a 30-day activity log, applied at startup and then daily.
* Fixed first-run routing: the health endpoint now reports whether the setup
  wizard has been completed, so a fresh install opens the wizard instead of
  landing on an empty dashboard.

## 0.1.0

Initial hobby release: BirdWeather and BirdNET-Go detection adapters, 16:9
collages, Samsung Frame delivery, Docker Compose deployment, and web setup.
