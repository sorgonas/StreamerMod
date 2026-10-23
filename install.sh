#!/usr/bin/env bash
# StreamerMod: system packages once as administrator, application always as user.
set -Eeuo pipefail
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
mode=install; prefix="${XDG_DATA_HOME:-$HOME/.local/share}/streamermod"; system_deps=1; dotnet=1; models=1; obs=1; opendeck=0; keyguard=1; shortcuts=1; target_uid=$(id -u)
usage() { cat <<'HELP'
Usage: bash install.sh [options]
  --prefix PATH       User installation directory
  --dry-run           Show the complete plan without changing anything
  --no-shortcuts      Do not create menu/command launchers (test installations)
  --skip-system       System dependencies have already been installed
  --without-obs       Do not install OBS when it is absent
  --without-dotnet    Do not install the .NET 10 SDK (C# unavailable without SDK)
  --without-models    Download speech models later in the app
  --with-opendeck     Install independent OpenDeck and the StreamerMod plugin
  --with-keyguard     Install the restricted timed-letter service (default)
  --without-keyguard  Skip the timed-letter service
  --help              Show this help
Standard: all Python features, audio utilities, .NET 10, Whisper Base, desktop launcher.
Supports Debian 12/13, Ubuntu 24.04+ and compatible derivatives with Python >=3.11.
Run as your normal desktop user. Administrator rights are requested only for system packages/services.
HELP
}
while (($#)); do
 case "$1" in
  --prefix) (($#>=2)) || { usage; exit 2; }; prefix=$2; shift;;
  --dry-run) mode=plan;; --skip-system) system_deps=0;; --without-obs) obs=0;;
  --without-dotnet) dotnet=0;; --without-models) models=0;; --no-shortcuts) shortcuts=0;; --with-opendeck) opendeck=1;; --with-keyguard) keyguard=1;; --without-keyguard) keyguard=0;;
  --system-stage) mode=system; shift; target_uid=${1:?UID missing};;
  --help|-h) usage; exit 0;; *) printf 'Unknown option: %s\n' "$1" >&2; exit 2;;
 esac; shift
done
[[ $(uname -s) == Linux ]] || { echo 'Linux is required.' >&2; exit 1; }
[[ -r /etc/os-release ]] || { echo '/etc/os-release is missing.' >&2; exit 1; }
# shellcheck disable=SC1091
source /etc/os-release
[[ " ${ID:-} ${ID_LIKE:-} " == *debian* || " ${ID:-} ${ID_LIKE:-} " == *ubuntu* ]] || { echo 'This installer supports apt-based Debian/Ubuntu systems.' >&2; exit 1; }
command -v apt-get >/dev/null || { echo 'apt-get is required.' >&2; exit 1; }
case $(uname -m) in x86_64|aarch64|arm64) ;; *) echo 'Only x86_64 and arm64 are supported by this installer.' >&2; exit 1;; esac
choose_package() { if apt-cache show "$1" >/dev/null 2>&1; then printf '%s' "$1"; else printf '%s' "$2"; fi; }
packages=(python3 python3-venv python3-pip python3-dev build-essential pkg-config curl ca-certificates unzip tar xz-utils
 ffmpeg pulseaudio-utils espeak-ng portaudio19-dev libportaudio2 libxcb-cursor0 libxkbcommon-x11-0 libegl1 libgl1
 libdbus-1-3 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-xinerama0 libxcb-xfixes0
 libgcc-s1 libstdc++6 libgssapi-krb5-2 zlib1g xdotool x11-utils)
packages+=("$(choose_package libasound2t64 libasound2)" "$(choose_package libglib2.0-0t64 libglib2.0-0)" "$(choose_package libssl3t64 libssl3)")
icu=$(apt-cache pkgnames | LC_ALL=C grep -E '^libicu[0-9]+$' | sort -V | tail -1 || true)
[[ -n "$icu" ]] || icu=libicu-dev
packages+=("$icu")
if ((obs)) && ! command -v obs >/dev/null && ! { command -v flatpak >/dev/null && flatpak info com.obsproject.Studio >/dev/null 2>&1; }; then packages+=(obs-studio); fi
if ((opendeck)); then packages+=(nodejs libayatana-appindicator3-1); fi
if ((keyguard)) && apt-cache show keyd >/dev/null 2>&1; then packages+=(keyd); fi
if [[ "$mode" == plan ]]; then
 printf 'Install directory: %s\nSystem package installation: %s\n' "$prefix" "$system_deps"
 printf 'apt packages:'; printf ' %s' "${packages[@]}"; printf '\n'
 printf '.NET 10 SDK: %s\nWhisper Base model: %s\nOpenDeck: %s\nTimed letter service: %s\n' "$dotnet" "$models" "$opendeck" "$keyguard"
 printf 'Python extras: desktop,voice,keyboard,camera,youtube\nNo accounts, streaming or microphone activation. Existing configuration is preserved.\n'; exit 0
fi
if [[ "$mode" == system ]]; then
 [[ $(id -u) == 0 && "$target_uid" =~ ^[0-9]+$ && "$target_uid" -ge 1000 ]] || { echo 'Root and a normal desktop UID are required.' >&2; exit 1; }
 apt-get update; apt-get install -y "${packages[@]}"
 python3 -c 'import sys; assert sys.version_info >= (3,11), "Python >=3.11 required"'
 if ((opendeck)); then bash "$project_dir/scripts/install-opendeck-system.sh"; fi
 if ((keyguard)); then bash "$project_dir/scripts/install-streamermod-keyguard.sh" "$target_uid"; fi
 exit 0
fi
[[ $(id -u) != 0 ]] || { echo 'Start as the normal desktop user. The installer requests administrator rights only when needed.' >&2; exit 1; }
if ((system_deps)); then
 stage=(bash "$project_dir/install.sh" --system-stage "$target_uid")
 ((obs)) || stage+=(--without-obs)
 ((opendeck)) && stage+=(--with-opendeck)
 ((keyguard)) && stage+=(--with-keyguard)
 ((keyguard)) || stage+=(--without-keyguard)
 if command -v pkexec >/dev/null && [[ -n ${DISPLAY:-}${WAYLAND_DISPLAY:-} ]]; then pkexec "${stage[@]}"
 elif command -v sudo >/dev/null; then sudo "${stage[@]}"
 elif command -v su >/dev/null; then printf -v stage_command '%q ' "${stage[@]}"; su -c "$stage_command"
 else echo 'Install system dependencies first using an administrator account, then use --skip-system.' >&2; exit 1
 fi
elif ((keyguard || opendeck)); then echo '--skip-system cannot install system services or OpenDeck; omit the feature flags or the skip option.' >&2; exit 2
fi
python3 -c 'import sys; assert sys.version_info >= (3,11), "Python >=3.11 required"'
args=(--prefix "$prefix")
((dotnet)) || args+=(--without-dotnet)
((models)) || args+=(--without-models)
((opendeck)) && args+=(--with-opendeck)
((shortcuts)) || args+=(--no-shortcuts)
exec python3 "$project_dir/scripts/install-user.py" "${args[@]}"
