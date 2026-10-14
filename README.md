# eero for OPNsense

See what your eero mesh Wi-Fi is doing from the OPNsense GUI: every eero unit, every client and
which unit it's on, and the network's settings. Read-only: changes stay in the eero app.

**Status: early development.** Sign-in, polling and roaming history work; the Devices, Clients and Network tabs are still placeholders.

## What it shows

- **Devices**: each eero unit: online or not, model, firmware, IP, wired or wireless backhaul
  (and which unit it hangs off), mesh quality, clients, uptime, radios and ports.
- **Clients**: every client: name, IP, MAC, which eero it's on, band, signal, link rate, and
  when it was last seen.
- **Network**: the eero network's settings and health: bridge or router mode, DHCP and DNS, band
  steering, WPA3, guest network, updates, last speed test.

## How it works

A small service on the router polls eero's cloud API, the same one the eero app uses, at a
gentle, rate-limited pace, and keeps the results in SQLite under `/var/db/eero/`. The GUI and
widget only read that copy, so opening a page never calls eero.

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
