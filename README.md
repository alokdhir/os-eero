# eero for OPNsense

See what your eero mesh Wi-Fi is doing from the OPNsense GUI: every eero unit, every client and
which unit it's on, and the network's settings. Read-only: changes stay in the eero app.

## What it shows

- **Units**: each eero unit: online or not, model, IP, wired or wireless backhaul (and which
  unit it hangs off), mesh quality, clients and uptime. Each unit has its own page: the clients on
  it now, its radios (channel, width, how busy), its ports and what is seen on them, firmware,
  power and serial number, and when it went offline or came back.
- **Clients**: every Wi-Fi client: name, which eero it's on, band and channel, signal, connection
  quality (eero's 0-5 bars), address, and when it was last seen. Each client has its own page with
  the time it spent on each eero and its moves between them; *Recent moves* lists the latest moves
  across all clients.
- **Network**: the eero network's settings and health: bridge or router mode, DHCP and DNS, band
  steering, WPA3, guest network, updates, last speed test.

## Better with Loupe

[Loupe](https://github.com/alokdhir/os-loupe) is a companion plugin for OPNsense: it shows which
device on your network talked to which site or service, how much data moved each way, and when.
It identifies each device from what the device says about itself (its Bonjour model, host name,
DHCP fingerprint, MAC vendor and the services it uses), so you see *Apple TV 4K*, *Smart plug* or
*Window shade* instead of an IP address or a chip maker.

eero only knows many devices by the maker of their Wi-Fi chip ("Tuya Smart Inc.", "Espressif
Inc."), so a house full of smart plugs, shades and fans shows up as rows of identical names. With
Loupe installed, this plugin uses what Loupe knows:

- **Names**: Loupe's name for each client: the name you gave it in the router's DHCP settings or in
  Loupe, or else what the device announces. A name set in the eero app still comes first.
- **Types and icons**: Loupe's device type and icon, which are more specific than eero's
  (often just "generic").
- **Makers**: the product's maker rather than its Wi-Fi module's ("Fanimation", not "Shenzhen
  Phaten Tech.").

Neither plugin needs the other. Without Loupe, this plugin shows what eero knows. Loupe works with
any network, eero or not, and does far more on its own: per-device traffic by service and site,
history over hours to a year, and searching which devices talked to a service or address.

## How it works

A small service on the router polls eero's cloud API, the same one the eero app uses, at a
gentle, rate-limited pace, and keeps the results in SQLite under `/var/db/eero/`. The GUI only
reads that copy, so opening a page never calls eero.

You log in once from the GUI: enter your eero account's email or phone, then the code eero
sends. The session is stored on the router in `/var/db/eero/` (readable by root only), not in
the OPNsense configuration, so it isn't in config backups. Your email or phone isn't stored.
Wi-Fi and Thread passwords that the API returns are dropped before anything is saved.

eero's API isn't public or documented, and eero can change it without notice. See
[docs/API.md](docs/API.md) for what the plugin uses.

## Install (development)

From a checkout, on a machine that can SSH to the router:

```sh
ROUTER=admin@192.168.1.1 tools/deploy.sh             # install or update
ROUTER=admin@192.168.1.1 tools/deploy.sh uninstall   # remove
```

Or on the router itself, as root: `sh tools/install.sh` (and `tools/uninstall.sh`).

## Credits

eero has never published its API. This plugin builds on the people who worked it out from the
eero app's traffic and shared what they found:

- [fulviofreitas/eero-api](https://github.com/fulviofreitas/eero-api) (MIT): the most complete
  and actively maintained client. Our reference for endpoints, fields, errors and the login
  flow. Its [Prometheus exporter](https://github.com/fulviofreitas/eero-prometheus-exporter)
  helped decide which fields are worth showing.
- [343max/eero-client](https://github.com/343max/eero-client) and
  [yepher/eeroMonitor](https://github.com/yepher/eeroMonitor): the early work that first
  documented the API and its login.

The plugin doesn't use eero-api directly: OPNsense plugins can only depend on FreeBSD packages,
and its dependencies aren't packaged. It talks to the API with Python's standard library and
`requests`, which OPNsense already ships.

eero is a trademark of eero LLC, an Amazon company. This project isn't affiliated with or
endorsed by eero or Amazon.

## License

BSD 2-Clause, see [LICENSE](LICENSE).
