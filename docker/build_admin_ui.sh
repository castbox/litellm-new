#!/bin/bash

set -euo pipefail

echo
pwd

if [ -f "enterprise/enterprise_ui/enterprise_colors.json" ]; then
    echo "Building Custom Admin UI..."
    cp enterprise/enterprise_ui/enterprise_colors.json ui/litellm-dashboard/ui_colors.json
else
    echo "Admin UI - using default LiteLLM UI colors"
fi

if ! command -v curl &> /dev/null; then
    if [[ "$(uname)" == "Darwin" ]]; then
        if ! command -v brew &> /dev/null; then
            echo "Error: Homebrew not found. Please install Homebrew and try again."
            exit 1
        fi
        brew update
        brew install curl
    elif command -v apt-get &> /dev/null; then
        apt-get update
        apt-get install -y curl
    elif command -v apk &> /dev/null; then
        apk update
        apk add curl
    else
        echo "Error: Unsupported package manager. Cannot install curl."
        exit 1
    fi
fi

cd ui/litellm-dashboard
chmod +x ./build_ui.sh
./build_ui.sh
cd ../..
