#!/bin/bash
set -euo pipefail

SERVICE_LINK="/service/venus-time-sync"

if [[ -e "$SERVICE_LINK" || -L "$SERVICE_LINK" ]]; then
    svc -dx "$SERVICE_LINK" 2>/dev/null || true
    svc -dx "$SERVICE_LINK/log" 2>/dev/null || true
    rm -f "$SERVICE_LINK"
fi

echo "venus-time-sync disabled; persistent state and rc.local entry retained"
