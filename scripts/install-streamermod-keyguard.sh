#!/bin/sh
# Run once as root; never grants general input-device/keyd access to the GUI.
set -eu
if [ "$(id -u)" -ne 0 ]; then echo 'Bitte in einem Root-Terminal ausführen.' >&2; exit 1; fi
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
target_uid=${1:-${SUDO_UID:-}}
case "$target_uid" in ''|*[!0-9]*) echo 'Ungültige Benutzer-ID' >&2; exit 1;; esac
if [ "$target_uid" -lt 1000 ]; then echo 'Normale Desktop-Benutzer-ID erforderlich' >&2; exit 1; fi
getent passwd "$target_uid" >/dev/null
if [ -d /etc/keyd ]; then
 for candidate in /etc/keyd/*.conf; do
  [ -f "$candidate" ] || continue
  if [ "$candidate" != /etc/keyd/streamermod.conf ]; then echo 'Vorhandene fremde keyd-Konfiguration: keine automatische Änderung.' >&2; exit 1; fi
 done
fi
/usr/bin/python3 -m py_compile "$script_dir/streamermod-keyguard.py"
if ! command -v keyd.rvaiya >/dev/null && ! command -v keyd >/dev/null; then
 if apt-cache show keyd >/dev/null 2>&1; then
  apt-get install -y keyd
 else
  # Debian 12 / Ubuntu 24.04: fixed official source, no unreviewed PPA.
  apt-get install -y build-essential curl ca-certificates
  work=$(mktemp -d);trap 'rm -rf -- "$work"' EXIT
  curl --fail --location --proto '=https' --tlsv1.2 'https://codeload.github.com/rvaiya/keyd/tar.gz/refs/tags/v2.5.0' -o "$work/keyd.tar.gz"
  printf '%s  %s\n' '93ec6c153ef673a7a8b4d8b686494dee11d182513f4531c71dce15a8db7f6c1c' "$work/keyd.tar.gz" | sha256sum --check --status
  mkdir "$work/source";tar -xzf "$work/keyd.tar.gz" --strip-components=1 -C "$work/source"
  make -C "$work/source";make -C "$work/source" install PREFIX=/usr
 fi
fi
keyd_binary=$(command -v keyd.rvaiya || command -v keyd)
install -d -m 0755 /usr/local/lib/streamermod /etc/keyd
install -o root -g root -m 0755 "$script_dir/streamermod-keyguard.py" /usr/local/lib/streamermod/keyguard.py
if [ ! -e /etc/keyd/streamermod.conf ]; then
 cat > /etc/keyd/streamermod.conf <<'CONFIG'
# StreamerMod-owned identity map; only timed A-Z bindings are applied by broker.
[ids]
*

[main]
CONFIG
fi
cat > /etc/systemd/system/streamermod-keyguard.service <<EOF
[Unit]
Description=StreamerMod restricted timed letter guard
Requires=keyd.service
After=keyd.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/lib/streamermod/keyguard.py --uid $target_uid
ExecStopPost=-$keyd_binary bind reset
Restart=on-failure
RestartSec=1
RuntimeDirectory=streamermod-keyguard
RuntimeDirectoryMode=0755
UMask=0077
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
RestrictAddressFamilies=AF_UNIX
CapabilityBoundingSet=CAP_CHOWN

[Install]
WantedBy=multi-user.target
EOF
chmod 0644 /etc/systemd/system/streamermod-keyguard.service
systemctl daemon-reload
systemctl enable --now keyd.service
systemctl restart keyd.service
systemctl enable --now streamermod-keyguard.service
systemctl restart streamermod-keyguard.service
systemctl is-active keyd.service streamermod-keyguard.service
printf '\nStreamermod-Tastensperre eingerichtet. Kein Abmelden nötig.\n'
