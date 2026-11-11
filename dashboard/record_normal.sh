
#!/usr/bin/env bash
# Record and validate one normal CAN run.
# Usage: bash dashboard/record_normal.sh <run_number> [seconds]

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN="${1:?Usage: bash dashboard/record_normal.sh <run_number> [seconds]}"
SECS="${2:-600}"
SIM="${SIM:-$ROOT/ecu_sim/ecu_simulator}"

if [[ ! "$RUN" =~ ^[1-3]$ ]]; then
    echo "ERROR: run number must be 1, 2, or 3."
    exit 1
fi

if [[ ! "$SECS" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: duration must be a positive whole number of seconds."
    exit 1
fi

if [[ ! -x "$SIM" ]]; then
    echo "ERROR: simulator is missing or not executable: $SIM"
    exit 1
fi

if ! python3 -c 'import can' 2>/dev/null; then
    echo "ERROR: python-can is not installed in this Python environment."
    exit 1
fi

if pgrep -x ecu_simulator >/dev/null 2>&1; then
    echo "ERROR: ecu_simulator is already running."
    echo "Stop the existing simulator before retrying."
    exit 1
fi

mkdir -p data
FILE="data/normal_run${RUN}_$(date +%m%d).csv"

if [[ -e "$FILE" ]]; then
    echo "ERROR: $FILE already exists; refusing to overwrite it."
    echo "Choose another run number or move the old file first."
    exit 1
fi

echo "Setting up vcan0..."
bash dashboard/setup_vcan.sh

SIM_PID=""

cleanup() {
    if [[ -n "$SIM_PID" ]] && kill -0 "$SIM_PID" 2>/dev/null; then
        kill -TERM "$SIM_PID" 2>/dev/null || true
        wait "$SIM_PID" 2>/dev/null || true
    fi
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "Starting simulator: $SIM"
"$SIM" >/dev/null &
SIM_PID=$!

sleep 1

echo "Recording normal run $RUN for $SECS seconds."
echo "Output: $FILE"

timeout --preserve-status --signal=INT --kill-after=5s \
    "${SECS}s" python3 dashboard/can_logger.py normal "$RUN"

cleanup
SIM_PID=""

if [[ ! -s "$FILE" ]]; then
    echo "ERROR: recording is missing or empty: $FILE"
    exit 1
fi

echo
echo "=== Recording summary ==="
wc -l "$FILE"
head -n 2 "$FILE"
tail -n 2 "$FILE"

echo
echo "=== CSV validation ==="
python3 dashboard/validate_csv.py "$FILE"

echo
echo "=== Baseline and counter checks ==="
python3 dashboard/check_baseline.py "$FILE"

echo
echo "Recording and checks completed: $FILE"
