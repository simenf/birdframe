# Local microphone and BirdNET-Go

BirdFrame delegates audio inference to the optional upstream BirdNET-Go
container. BirdFrame consumes its detection stream and never needs access to
`/dev/snd` itself.

## Start and configure

```sh
docker compose --profile local-audio up -d
docker compose logs --tail=100 birdnet-go
```

On Linux, check available capture devices on the host:

```sh
arecord -l
ls -l /dev/snd
```

Open BirdNET-Go from the advanced administration link in BirdFrame, select the
USB/ALSA device, set its own location and detection threshold, and perform a
live-input test. Configure BirdFrame's separate display threshold/cooldown in
its own settings; those do not change the BirdNET-Go scientific record.

## Model handling

BirdFrame does not redistribute model weights. The normal BirdNET-Go image
includes its upstream default model. If an optional model is available, use the
BirdNET-Go model gallery/administration flow, read its license, and allow the
upstream service to download it into `birdnet-go-data/`. BirdFrame shows model
status and links to the upstream controls.

## Common failures

- **No device in the sidecar:** confirm `/dev/snd` exists before the container
  starts, then restart the `birdnet-go` service. Containers cannot access a USB
  device that the host does not expose.
- **Permission denied:** inspect the host's sound-device group and run the
  upstream image according to its documented device-permission guidance.
- **Container is running but BirdFrame is disconnected:** ensure `BIRDNET_GO_URL`
  is `http://127.0.0.1:8080` for this host-network Compose file, and check the
  upstream SSE endpoint from the Linux host.
- **Slow inference:** reduce BirdNET-Go processing load, use a faster host, or
  switch BirdFrame to BirdWeather mode. Do not reduce display cooldown as a
  substitute for fixing audio inference.
