#!/bin/bash

set -euo pipefail

RAW_NODE_VERSION="${NODE_VERSION:-20}"
NODE_VERSION="${RAW_NODE_VERSION#v}"
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"

if [ ! -s "$NVM_DIR/nvm.sh" ]; then
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.38.0/install.sh | bash
fi

[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

nvm install "$NODE_VERSION"

# `nvm install` already activates the resolved version. Avoid a follow-up
# `nvm use v20` in minimal BusyBox-based images, where nvm's alias lookup can
# trip over the bundled `ls` implementation.
node --version
npm --version

# print contents of ui_colors.json
echo "Contents of ui_colors.json:"
cat ui_colors.json

# Docker builds copy the dashboard source without node_modules, and local
# worktrees can also have a stale dependency tree. Ensure the install is
# present and healthy before attempting `next build`.
if ! npm ls --depth=0 > /dev/null 2>&1; then
  if [ -f package-lock.json ]; then
    npm ci --no-audit --no-fund
  else
    npm install --no-audit --no-fund
  fi
fi

# Run npm build
npm run build

# Check if the build was successful
if [ $? -eq 0 ]; then
  echo "Build successful. Copying files..."

  # echo current dir
  echo
  pwd

  # Specify the destination directory
  destination_dir="../../litellm/proxy/_experimental/out"

  # Remove existing files in the destination directory
  rm -rf "$destination_dir"/*

  # Copy the contents of the output directory to the specified destination
  cp -r ./out/* "$destination_dir"

  rm -rf ./out

  echo "Deployment completed."
else
  echo "Build failed. Deployment aborted."
fi
