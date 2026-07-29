# BirdWeather

BirdWeather is a detection input alternative, not an audio-upload feature.
BirdFrame polls an existing station's avian detections using the station token
you enter in Settings or the setup wizard.

1. Create/select a station in BirdWeather and obtain the token authorized for
   its detections.
2. Start BirdFrame normally; do **not** enable `local-audio`.
3. Choose BirdWeather as the one active source, enter the token, and run the
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
