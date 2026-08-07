#!/usr/bin/env bash
# Downloads the standalone Tailwind CSS CLI binary into bin/tailwindcss.
# No Node/npm required — see docs/development.md for why.
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p bin

os="$(uname -s)"
arch="$(uname -m)"

case "$os" in
    Linux) platform="linux" ;;
    Darwin) platform="macos" ;;
    *) echo "Unsupported OS: $os. Download manually from https://github.com/tailwindlabs/tailwindcss/releases" >&2; exit 1 ;;
esac

case "$arch" in
    x86_64|amd64) platform_arch="${platform}-x64" ;;
    arm64|aarch64) platform_arch="${platform}-arm64" ;;
    *) echo "Unsupported architecture: $arch" >&2; exit 1 ;;
esac

url="https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-${platform_arch}"
echo "Downloading $url ..."
curl -sL "$url" -o bin/tailwindcss
chmod +x bin/tailwindcss
echo "Installed bin/tailwindcss"
./bin/tailwindcss --help | head -1
