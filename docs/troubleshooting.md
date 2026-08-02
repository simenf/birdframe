# Troubleshooting and recovery

Start with service state and recent logs:

```sh
docker compose ps
docker compose logs --tail=150 birdframe
docker compose --profile local-audio logs --tail=150 birdnet-go
```

Do not paste tokens, precise coordinates, pairing tokens, or signed package URLs
into issue reports. Use the dashboard's diagnostics export, which redacts
secrets, when available.

| Symptom | Checks |
| --- | --- |
| UI does not load | Confirm `BIRDFRAME_PORT` is free, the container is healthy, and the Linux firewall permits trusted-LAN access. |
| BirdWeather test fails | Verify the station token at BirdWeather, then inspect status/backoff logs without revealing it. 
| BirdFrame cannot reach BirdNET-Go | This Compose configuration uses host networking: set `BIRDNET_GO_URL=http://127.0.0.1:8080`, then inspect upstream logs. |
| TV discovery or wake fails | Use manual IP, same subnet, disable client isolation, and test each Art Mode operation separately. See [samsung-frame.md](samsung-frame.md). |
| Package install fails | Check catalog URL, download reachability, checksum, package compatibility, and free space. Never bypass checksum errors. |
| Artwork is missing/odd | Review asset approval status, anatomy checks, available storage, OpenRouter job errors, and composition safe-area settings. |

## Safe restart

```sh
docker compose restart birdframe

```
Jobs and cursor state are persisted and should resume safely. A restart does not
delete artwork or TV pairing state.

## Backups and disaster recovery

Stop services and archive `data/` plus `birdnet-go-data/` if used. The BirdFrame
database and `secret.key` are a pair: restoring a database encrypted with a
different key prevents secret decryption. Restore both together, preserve file
ownership, then restart. If the key is irretrievably lost, reset affected
provider/TV credentials through the wizard rather than trying to decrypt them.
