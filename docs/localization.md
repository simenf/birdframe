# Localization and Norwegian names

BirdFrame resolves the name shown in the natural-history legend by scientific
name, not by the English common name sent by BirdWeather or BirdNET-Go. The
repository includes the current BirdLife Norge / Norsk navnekomité for fugl
(NNKF) AviList 2025 workbook import: `backend/birdframe/data/no_names.json`.

To update it when BirdLife publishes a new workbook:

```sh
python scripts/import-norwegian-bird-names.py AviListNNKF.xlsx
```

The importer uses only the Python standard library and extracts the
`Scientific_name` → `norskAviListv1` columns. It produces a sorted UTF-8 JSON
file, which is bundled into the Docker image and loaded locally at render time.

Additional locales use the same format: add a file named
`backend/birdframe/data/<locale>_names.json`, keyed by scientific name, then
select that locale when the UI supports it. Local additions take precedence
over the English detection name; the small built-in Norwegian map remains a
fallback for installations that have not imported the data yet.

BirdLife’s list is the authoritative source for this project’s Norwegian bird
names. It is separate from the narrower Norgeslisten, which only covers birds
recorded within Norway.
