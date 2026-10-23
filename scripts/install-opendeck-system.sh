#!/usr/bin/env bash
# Independent upstream OpenDeck, fixed release and verified upstream asset digest.
set -Eeuo pipefail
[[ $(id -u) == 0 ]] || { echo 'Administrator rights required.' >&2; exit 1; }
if command -v opendeck >/dev/null; then echo 'Existing OpenDeck installation preserved.'; exit 0; fi
version=2.14.2
case $(dpkg --print-architecture) in
 amd64) arch=amd64; expected=0ba2edda22c6f69d1b57bbd291676b9c3e1614cb654929ad20795379adc72406;;
 arm64) arch=arm64; expected=f1f73beb85a194ff3719af7ea02b3e67a8af805b7c1d5d2aae6efbff0c728844;;
 *) echo 'No supported OpenDeck deb for this architecture.' >&2; exit 1;;
esac
folder=$(mktemp -d);trap 'rm -rf -- "$folder"' EXIT
chmod 0755 "$folder";package="$folder/opendeck.deb"
curl --fail --location --proto '=https' --tlsv1.2 --retry 2 "https://github.com/nekename/OpenDeck/releases/download/v$version/opendeck_${version}_${arch}.deb" --output "$package"
printf '%s  %s\n' "$expected" "$package" | sha256sum --check --status
chmod 0644 "$package";apt-get install -y "$package" libayatana-appindicator3-1 nodejs xdotool x11-utils
udevadm control --reload-rules;udevadm trigger --subsystem-match=usb --attr-match=idVendor=0fd9;udevadm trigger --subsystem-match=hidraw
printf 'OpenDeck installed independently. Reconnect the Stream Deck if USB access is not yet available.\n'
