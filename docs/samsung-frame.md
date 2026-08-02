# Samsung The Frame

BirdFrame uses the community `samsungtvws` implementation of Samsung's private
TV WebSocket/Art Mode interface. It is useful, but not an official Samsung API;
behavior differs by model year and firmware. Manual IP configuration is always
available because LAN discovery is not reliable across VLANs and routers.

## Pairing

1. Put the host and TV on the same trusted LAN/subnet.
2. In BirdFrame, select the discovered TV or enter its IPv4 address manually.
3. Click send image to tv. 
4. The tv should ask for confirmation and you need to allow you app access to control the tv.

The final artwork is a JPEG rendered locally at the TV's selected profile
(normally 3840×2160). BirdFrame records every content ID it uploads and only
ever deletes a previous BirdFrame-owned upload after a replacement succeeds.

## Behavior controls

Settings provide the matte, upload cadence, quiet hours, and an explicit
**allow wake** option. Automatic wake uses Wake-on-LAN and needs the TV's MAC
address (Settings → Display & TV) with network standby enabled on the TV;
wake is disabled until both are configured. Automatic TV updates are skipped
during the configured quiet hours, interpreted in the location timezone
selected in the setup wizard. A burst of detections is coalesced, so normal
operation sends no more than one new composition per configured interval (five
minutes by default).

**Automatically select new artwork on TV** is enabled by default. BirdFrame
checks for a newer rendered composition, uploads it at the configured cadence,
and calls Samsung Art Mode's `select_image(..., show=true)` so the Frame
switches to it immediately. Turn this off to retain manual **Send current art
to TV** control.


## Other Samsung TVs (Ambient Mode)

Non-Frame Samsung TVs with Ambient Mode cannot receive pushed images through a
local API. 

Other Samsung TVs — and any screen — can still show the exact same
artwork through the generic display API (`/api/v1/display/current.jpg`) in a
browser or media player, without the frame matte and selection controls.
