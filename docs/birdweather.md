# BirdWeather

BirdWeather is a detection input alternative, not an audio-upload feature.
BirdFrame supports two separate BirdWeather modes:

- **Public BirdWeather station** reads public avian detections by numeric
  station ID and needs no token. For example, enter `2505` for
  `PUC-2505-Oslo Norway`.
- **My BirdWeather station** uses BirdWeather's authenticated REST API and
  requires the station token authorized for that station.

Public mode queries BirdWeather's public GraphQL API every polling interval and
de-duplicates detections locally. It only has access to information the station
operator has made public; it cannot upload, edit, or access private station
data.

For an authenticated station, BirdFrame polls avian detections using the token
you enter in Settings or the setup wizard.

1. Create/select a station in BirdWeather and obtain the token authorized for
   its detections.
2. Start BirdFrame normally; do **not** enable `local-audio`.
3. Choose **My BirdWeather station** as the one active source, enter the token, and run the
   connection test.
4. Set a conservative polling interval (15 seconds is the default) and save.

BirdFrame saves a cursor and processed detection IDs so polling/restarts do not
duplicate history. It does not download soundscapes by default. The token is
encrypted at rest, redacted from logs, and is distinct from every other API
credential.

Station history can also rank species for regional pre-generation. Its score is
shown as **station frequency**, not ecological occurrence probability.

If testing fails, first verify the token/station in BirdWeather, then check the
BirdFrame log for the HTTP status (without sharing the token). Backoff protects
the service after temporary errors; avoid reducing the interval to compensate.
