#!/bin/bash
set -eo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

if [ ! -f "enterprise/enterprise_ui/enterprise_colors.json" ]; then
    echo "Admin UI - using the default UI compiled by the ui-builder stage"
    exit 0
fi

exec bash ui/litellm-dashboard/build_ui.sh
