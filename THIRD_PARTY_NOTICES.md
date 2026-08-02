# Third-party notices

BirdFrame is a non-commercial hobby project. This file is a notice, not a
replacement for reviewing each dependency's current license before release.

| Component | Purpose | License / important note |
| --- | --- | --- |
| [BirdNET-Go](https://github.com/tphakala/birdnet-go) | Optional local audio recognition sidecar | Check the upstream repository and image release for its current license and model terms. BirdFrame does not copy its model weights. |
| [BirdNET Analyzer/models](https://github.com/birdnet-team/BirdNET-Analyzer) | Recognition model technology used by BirdNET-Go | The upstream project states non-commercial terms; commercial deployment requires separate permission. |
| [samsung-tv-ws-api](https://github.com/xchwarze/samsung-tv-ws-api) | Samsung TV WebSocket/Art Mode client | Samsung Art Mode is an unofficial/private interface and may change by firmware. |
| [AvianVisitors](https://github.com/Twarner491/AvianVisitors) | Product and art-pipeline inspiration | BirdFrame independently reimplements the ideas described by the project; it does not include its code or artwork. |
| [willmanidis2's AvianVisitors fork — frame-journal-layout](https://github.com/willmanidis2/AvianVisitors/tree/feat/frame-journal-layout) | Journal-page display mode inspiration | The Field Journal view re-implements that fork's layout (longhand date, species grid, handwritten counts) with BirdFrame's own Pillow renderer; no code or artwork is copied. |
| [Caveat](https://github.com/google/fonts/tree/main/ofl/caveat) | Handwriting script bundled in `backend/birdframe/data/fonts/` | SIL Open Font License 1.1 (see `Caveat-OFL.txt`); © 2014 Pablo Impallari. |
| [Libre Baskerville](https://github.com/google/fonts/tree/main/ofl/librebaskerville) | Serif typeface bundled in `backend/birdframe/data/fonts/` | SIL Open Font License 1.1 (see `LibreBaskerville-OFL.txt`); © 2012 The Libre Baskerville Project Authors. |
| [OpenRouter](https://openrouter.ai) | User-selected image-generation provider | Users supply their own key and must comply with the selected model's terms. Generated assets can have model/provider-specific terms. |
| [BirdWeather](https://www.birdweather.com) | Optional detection-source API | Public station data needs no credential; private/token-scoped requests require a user-supplied token and must comply with BirdWeather terms. |
| [BirdLife Norway / Norsk navnekomité for fugl](https://www.birdlife.no/fuglekunnskap/navn/) | Norwegian species names bundled in `backend/birdframe/data/no_names.json` | Source data is maintained by BirdLife Norway; review its current terms and attribution requirements before redistribution. |

Python, JavaScript, operating-system, and transitive dependencies are recorded
in the release build's dependency metadata. A production release should add
the exact versioned dependency notices generated from its lockfiles.

Artwork packages are not covered by the BirdFrame project license unless their
own manifest explicitly says so. Every package must include `LICENSES/` and
`attribution.json`.

The original AvianVisitors `cutouts/` assets are optional bird-detail/fallback
images and are not required by BirdFrame's collage-compatible pack format.
