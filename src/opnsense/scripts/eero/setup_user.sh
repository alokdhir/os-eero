#!/bin/sh

# The user eero runs as, and its data. Run as root: by the rc script at each start and by the installers.
# The uid is fixed (below 2000, which OPNsense leaves alone) so files keep their owner across a reinstall.

pw usershow eero >/dev/null 2>&1 || \
	pw useradd eero -u 1788 -d /nonexistent -s /usr/sbin/nologin -c "eero status poller" || exit 1
mkdir -p /var/db/eero
chown -R eero:eero /var/db/eero
chmod 700 /var/db/eero
