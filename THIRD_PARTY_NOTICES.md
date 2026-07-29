# Third-party notices

BirdFrame is a non-commercial hobby project. This file is a notice, not a
replacement for reviewing each dependency's current license before release.

| Component | Purpose | License / important note |
| --- | --- | --- |
| [BirdNET-Go](https://github.com/tphakala/birdnet-go) | Optional local audio recognition sidecar | Check the upstream repository and image release for its current license and model terms. BirdFrame does not copy its model weights. |
| [BirdNET Analyzer/models](https://github.com/birdnet-team/BirdNET-Analyzer) | Recognition model technology used by BirdNET-Go | The upstream project states non-commercial terms; commercial deployment requires separate permission. |
| [samsung-tv-ws-api](https://github.com/xchwarze/samsung-tv-ws-api) | Samsung TV WebSocket/Art Mode client | Samsung Art Mode is an unofficial/private interface and may change by firmware. |
| [AvianVisitors](https://github.com/Twarner491/AvianVisitors) | Product and art-pipeline inspiration | BirdFrame independently reimplements the ideas described by the project; it does not include its code or artwork. |
| [OpenRouter](https://openrouter.ai) | User-selected image-generation provider | Users supply their own key and must comply with the selected model's terms. Generated assets can have model/provider-specific terms. |
| [BirdWeather](https://www.birdweather.com) | Optional detection-source API | Users supply their own station token and must comply with BirdWeather terms. |

Python, JavaScript, operating-system, and transitive dependencies are recorded
in the release build's dependency metadata. A production release should add
the exact versioned dependency notices generated from its lockfiles.

Artwork packages are not covered by the BirdFrame project license unless their
own manifest explicitly says so. Every package must include `LICENSES/` and
`attribution.json`.
