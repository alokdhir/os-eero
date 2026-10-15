# eero API notes

The eero app talks to a private cloud API. eero has never published it; what's here comes from
[fulviofreitas/eero-api](https://github.com/fulviofreitas/eero-api) (MIT, the most active
reverse-engineered client, used as our reference) and from read-only calls against a real
network on eeroOS 7.17 in bridge mode (2026-10-14). Anything marked *unverified* hasn't been seen
on a real network yet.

## Basics

- Base URL `https://api-user.e2ro.com`, version `2.2` for everything we read.
- Session: header `Cookie: s=<token>`. There is no separate refresh token.
- `User-Agent`: eero-api sends `eero-ios/2026.8.1 (iPhone; iOS 18.5)`; we do the same.
- Envelope: `{"meta": {"code": 200, "server_time": "…"}, "data": …}`. Errors carry
  `meta.error`, a dotted code (`error.session.invalid`).
- Resource URLs come back as paths (`/2.2/networks/<id>`, `/2.2/eeros/<id>`). Store and follow
  them; don't build ids into paths by hand.
- No rate-limit headers on responses (no `X-RateLimit-*`, no `Retry-After` on success).
  Responses take 0.3–1.8 s.

## Errors

| HTTP | `meta.error` | Meaning | What we do |
|---|---|---|---|
| 401 | `error.session.invalid` / `.expired` / `.revoked` | Session gone (seen: `invalid` for a bad token and for no cookie) | Stop polling, status `needs_login` |
| 401 | `error.session.refresh` | Session valid but must be refreshed (*unverified*) | `POST /2.2/login/refresh` once, retry the call once |
| 401 | `error.verification.*`, `error.login.*`, `error.too.many.resends` | Login flow problems | Show in the login dialog |
| 403 | `error.access.denied` | Not allowed (seen on `/transfer`) | Treat as "not available", stop asking |
| 404 | none; body is `{"error": {"statusCode": 404, …}}` without `meta` | Unknown endpoint | Treat as "not available" |
| 429, or any status with `error.rate.limit` | Rate limited (*unverified*; never provoked on purpose) | Back off, honour `Retry-After` if present |

## Login (from eero-api; *unverified* here: our dev token came from the same flow)

1. `POST /2.2/login` with `{"login": "<email or phone>"}` → `data.user_token`; eero emails or
   texts a code.
2. `POST /2.2/login/verify` with `{"code": "…"}` and `Cookie: s=<user_token>` → session valid.
3. `POST /2.2/login/refresh` when asked to (above). `POST /2.2/login/resend` re-sends the code.
4. `POST /2.2/logout`: form body with one field literally named `Cookie` = `s=<token>`.

## What we read

Everything below is `GET`. Paths are relative to the network URL from `/2.2/account`
(`data.networks.data[].url`) unless they start with `/2.2/`.

| Endpoint | Size* | Gives us | Poll |
|---|---|---|---|
| `/2.2/account` | 1 KB | Network list (`url`, `name`) | start, then hourly |
| `(network)/eeros` | 37 KB | Units: everything for the Units tab | 60 s |
| `(network)/devices` | 240 KB | Clients: everything for the Clients tab | 60 s |
| `(network)` | 60 KB | Settings, health, updates, last speed test, guest network; also embeds the units list | 5 min |
| `(network)/speedtest` | 1 KB | Speed test history | hourly |
| `(network)/thread` | <1 KB | Thread on/off, channel, name | hourly |
| `/2.2/eeros/<id>/connections` | 5 KB | Per-unit ports (speed, upstream port) and its wireless clients | on demand only (one call per unit) |

\* For a network with 10 units and ~115 clients. About 3 requests a minute at these rates.

Not used: `/routing`, `/reservations`, `/forwards` (empty in bridge mode, and the router owns
those now), `/profiles` (150 KB, parental controls), `/diagnostics` (only `{status}`), `/support`
(eero's contact details), `/updates` (same as the network's `updates` object), `/ac_compat`.
`/transfer` returns 403 and `/settings`, `/burst_reporters` 404 on this network.

## What we change

The only change the plugin makes (decided 2026-10-15):

| Call | Body | Use |
|---|---|---|
| `PUT /2.2/eeros/<id>` (the unit's `url`) | form `location=<name>` | Rename a unit (the name the app shows). From eero-api's `set_location`. Verified 2026-10-15: the next GET returned the new name; eero accepts a name another unit already has |

Each unit also lists `resources.reboot` (`/2.2/eeros/<id>/reboot`), so a single unit can be rebooted as well as the whole network (`POST <network>/reboot`). Not used yet (EERO-8).

## Secrets in responses: never cache, log or show

The network object and others carry credentials. Strip them before anything is written to the
cache:

- network: `password` (the Wi-Fi password), `guest_network.password`,
  `guest_network.resources.password`
- `/thread`: `master_key`, `commissioning_credential`, `xpan_id`, `pan_id`

The client strips a fixed list of keys; anything new that looks like a secret should be added to
that list.

## Fields

### Units (`/eeros`, our "Units" tab)

| Field | Example / values | Use |
|---|---|---|
| `url` | `/2.2/eeros/<id>` | Key |
| `location` | `Hallway` | Name shown |
| `model`, `model_number` | `eero Pro 6` | |
| `serial` | | Detail only |
| `status`, `state`, `heartbeat_ok`, `last_heartbeat` | `green`, `ONLINE`, `true` | Online/offline |
| `ip_address` | | Match to router leases by IP, not MAC (`mac_address` isn't the MAC it uses for DHCP) |
| `mac_address`, `ethernet_addresses[]` | | Detail only |
| `os_version`, `update_available` | `v7.17.2-139` | Firmware |
| `connection_type`, `wired` | `WIRED`, `WIRED_POE`, `WIRELESS` | Backhaul |
| `wireless_upstream_node` | `null` when wired; else `{name, primary_mesh_radio, node_or_proxied_node_id, is_proxied_node}` | Upstream unit. `name` matches the upstream's `location`; `node_or_proxied_node_id` is *not* the id in its `url` |
| `mesh_quality_bars` | 0–5 | Backhaul quality |
| `is_primary_node`, `gateway`, `using_wan` | | Role. `is_primary_node` is eero's gateway eero. In bridge mode every unit reports `gateway: false`, `using_wan: false`, but one is still primary, and eero moves the role: with the primary's wired port disabled (it stayed online over wireless backhaul) another wired unit became primary within ~2 min, and the original took it back ~1 min after its port returned (tested 2026-10-15). No API call sets it. |
| `connected_clients_count`, `…_wired_…`, `…_wireless_…` | | Clients per unit |
| `uptime.since_last_reboot_s`, `last_reboot` | | Uptime |
| `bands[]`, `radio_channel_stats.band_*` | channel, width, utilization %, client count, tx power | Radio detail. Keys: `band_2_4GHz`; `band_5GHz_low` + `band_5GHz_high` on tri-band units, `band_5GHz_full` on dual-band ones |
| `ethernet_status.statuses[]` | `port_name`, `hasCarrier`, `speed` (`P1000`; `P10` on a port with no link), `isWanPort` (the uplink on wired units), `isLeafWiredToUpstream`, `lldpInfo[]` | Port detail. `lldpInfo` lists every LLDP speaker on the port's network, not just the next hop: other eero units (`systemName` `eero`, matched by `managementIpv4Address`), other devices by `systemName`, switch ports by `portId`. `neighbor` was always null |
| `power_info.power_source` | `ETHERNET` (PoE; metadata `port`, `negotiated_power`), `USB` (adapter) | Power |
| `resources.connections`, `resources.reboot` | paths | Connections; reboot (later) |

### Clients (`/devices`)

| Field | Example / values | Use |
|---|---|---|
| `url`, `mac` | | Key (MAC; `is_private` = randomised MAC) |
| `nickname`, `hostname`, `display_name` | | Name: nickname, else display name |
| `manufacturer`, `device_type`, `model_name` | `phone`, `printer`, `generic` | |
| `ip`, `ips[]`, `ipv6_addresses[]` | | |
| `connected`, `last_active`, `first_active` | | Online now / last seen; the list includes disconnected clients |
| `wireless`, `connection_type` | `wireless` / `wired` | |
| `source.location`, `source.url` | | **Which unit the client is on** |
| `interface.frequency` | `2.4`, `5` | Band |
| `connectivity.signal`, `signal_avg`, `snr`, `score_bars` | | Signal |
| `connectivity.rx_bitrate`, `tx_rate_info`, `rx_rate_info` | | Link rate |
| `connectivity.packet_stats`, `tx_retry_pct` | | Link quality detail |
| `usage.down_mbps`, `usage.up_mbps` | | Current throughput |
| `profile.name`, `paused`, `blacklisted`, `is_guest` | | Detail only |

### Network (the network object, our "Network" tab)

| Field | Values seen | |
|---|---|---|
| `name`, `status` | `connected` | |
| `gateway`, `connection.mode` | `bridged` | Bridge vs router mode |
| `health.internet.status`, `health.internet.isp_up`, `health.eero_network.status` | | |
| `dhcp.mode`, `dns.mode`, `dns.caching`, `lease.mode` | `automatic`, `dhcp` | |
| `wan_type`, `ip_settings.public_ip`, `ip_settings.double_nat` | | |
| `band_steering`, `wpa3`, `wireless_mode`, `mlo_mode`, `upnp`, `thread`, `homekit.enabled` | | |
| `guest_network.enabled`, `guest_network.name` | | (not the password) |
| `updates.has_update`, `target_firmware`, `preferred_update_hour`, `last_update_started` | | |
| `speed.down`, `speed.up`, `speed.date` | | Last speed test |
| `online_eeros_count`, `offline_eeros_count`, `clients.count` | | Summary/widget |
| `auto_setup_mode`, `timezone` | | |

## Test fixtures

`tests/fixtures/` holds synthetic responses in these shapes (documentation addresses, `02:00:…`
MACs, made-up names and ids), written by hand from the field lists above, never copied from a
real network. `error_session_refresh` and `error_rate_limit` follow eero-api's description; we
haven't seen either from the server. One client name contains quotes and markup on purpose, to
test escaping.
