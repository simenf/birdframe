# Local microphone and BirdNET-Go

BirdFrame delegates audio inference to the optional upstream BirdNET-Go
container. BirdFrame consumes its detection stream and never needs access to
`/dev/snd` itself.

Go check birdnet-go on how to setup.