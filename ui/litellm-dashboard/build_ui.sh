#!/bin/bash
set -eo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"
requested_node_version="${NODE_VERSION:-$(cat .nvmrc)}"
requested_node_version="${requested_node_version#v}"

if ! command -v node >/dev/null || [ "$(node --version)" != "v${requested_node_version}" ]; then
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  if [ ! -s "$NVM_DIR/nvm.sh" ]; then
    NVM_VERSION="v0.40.4"
    NVM_CHECKSUM="4b7412c49960c7d31e8df72da90c1fb5b8cccb419ac99537b737028d497aba4f"
    NVM_SCRIPT=$(mktemp)
    trap 'rm -f "$NVM_SCRIPT"' EXIT
    curl -fsSL "https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_VERSION}/install.sh" -o "$NVM_SCRIPT"
    if command -v sha256sum >/dev/null; then
      echo "${NVM_CHECKSUM}  ${NVM_SCRIPT}" | sha256sum -c -
    else
      echo "${NVM_CHECKSUM}  ${NVM_SCRIPT}" | shasum -a 256 -c -
    fi
    bash "$NVM_SCRIPT"
  fi
  source "$NVM_DIR/nvm.sh" --no-use
  nvm install "$requested_node_version"
fi

if ! npm ls --depth=0 >/dev/null 2>&1; then
  if [ -f package-lock.json ]; then
    npm ci
  else
    npm install
  fi
fi

npm run build
destination_dir="$script_dir/../../litellm/proxy/_experimental/out"
rm -rf "$destination_dir"
mkdir -p "$destination_dir"
cp -R ./out/. "$destination_dir/"
rm -rf ./out
echo "Admin UI build completed"
