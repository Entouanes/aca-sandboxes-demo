set -euo pipefail

NODE_VERSION=22.23.3
COPILOT_VERSION=1.0.97
case "$(uname -m)" in
  x86_64) arch=x64 ;;
  aarch64) arch=arm64 ;;
  *) echo "Unsupported architecture" >&2; exit 1 ;;
esac

prefix="$HOME/.local"
node_dir="$prefix/share/node"
mkdir -p "$node_dir" "$prefix/bin" "$HOME/workspace"
export PATH="$node_dir/bin:$prefix/bin:$PATH"

archive=$(mktemp)
sums=$(mktemp)
trap 'rm -f "$archive" "$sums"' EXIT
filename="node-v$NODE_VERSION-linux-$arch.tar.gz"
base="https://nodejs.org/dist/v$NODE_VERSION"
curl --fail --silent --show-error --location --max-time 60 "$base/$filename" -o "$archive"
curl --fail --silent --show-error --location --max-time 30 "$base/SHASUMS256.txt" -o "$sums"
expected=$(awk -v file="$filename" '$2 == file { print $1 }' "$sums")
test -n "$expected"
printf '%s  %s\n' "$expected" "$archive" | sha256sum --check >&2
tar -xzf "$archive" --strip-components=1 -C "$node_dir"
npm install --global --prefix "$prefix" "@github/copilot@$COPILOT_VERSION" >&2
printf '\nexport PATH="$HOME/.local/share/node/bin:$HOME/.local/bin:$PATH"\n' >> "$HOME/.profile"
cd "$HOME/workspace"
copilot --version
touch "$HOME/.launchpad-ready"
