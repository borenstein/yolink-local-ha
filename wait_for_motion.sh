#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
  --7804)
    device_id="${YOLINK_MOTION_7804_SERIAL:-}"
    shift
    ;;
  --7805)
    device_id="${YOLINK_MOTION_7805_SERIAL:-}"
    shift
    ;;
  *)
    echo "Usage: $0 --7804|--7805 [args...]" >&2
    exit 2
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/wait_for_yolink_change.py" \
  --kind motion \
  --device-id "${device_id}" \
  "$@"
