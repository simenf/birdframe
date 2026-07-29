# Samsung The Frame

BirdFrame uses the community `samsungtvws` implementation of Samsung's private
TV WebSocket/Art Mode interface. It is useful, but not an official Samsung API;
behavior differs by model year and firmware. Manual IP configuration is always
available because LAN discovery is not reliable across VLANs and routers.

## Pairing

1. Put the host and TV on the same trusted LAN/subnet.
2. In BirdFrame, select the discovered TV or enter its IPv4 address manually.
3. Start pairing and accept the authorization prompt on the TV.
4. Run the upload test. BirdFrame records the pairing token in `data/` and
   removes only the test image it created.

The final artwork is a JPEG rendered locally at the TV's selected profile
(normally 3840×2160). BirdFrame records every content ID it uploads and only
ever deletes a previous BirdFrame-owned upload after a replacement succeeds.

## Behavior controls

Settings provide the matte, upload cadence, retries, quiet hours, and an
explicit **allow wake** option. Wake-on-LAN is disabled until selected. A burst
of detections is coalesced, so normal operation sends no more than one new
composition per configured interval (five minutes by default).

## Diagnostics

Test connection, upload, select, and delete separately in Settings. For a
failure, collect the support bundle and record the TV model/year, firmware,
network arrangement, and which operation failed. Never include the pairing
token in a bug report.

Check these first:

- TV is powered/reachable and permission prompts are visible.
- Host and TV are on the same subnet, without client/AP isolation.
- No other controller is repeatedly replacing Art Mode content.
- The configured IP has not changed; reserve it in DHCP if possible.
- The host uses native Linux networking; Docker Desktop discovery is not a
  supported hardware-control path.

Firmware may remove or alter Art Mode behavior. BirdFrame cannot guarantee
support for every Frame model. The generic display API remains available for
other displays even if direct TV control is unavailable.
