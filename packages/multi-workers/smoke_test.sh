#!/usr/bin/env bash
# smoke_test.sh — E2E Level 2 verification for agent-team-loop
# Run in Git Bash on Windows. Requires: python3, node, netstat
# Usage: bash smoke_test.sh [--project-dir <path>]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MW_PY="$SCRIPT_DIR/mw.py"
TEST_DIR="${1:-/tmp/test project}"   # AC-015: path with space
PASS=0
FAIL=0
ERRORS=()

_pass() { echo "PASS: $1"; ((PASS++)) || true; }
_fail() { echo "FAIL: $1"; ERRORS+=("$1"); ((FAIL++)) || true; }
_assert() { if eval "$1"; then _pass "$2"; else _fail "$2"; fi; }

# ── Cleanup ────────────────────────────────────────────────────────────────────
cleanup() {
    python3 "$MW_PY" stop --project="$TEST_DIR" 2>/dev/null || true
    rm -rf "$TEST_DIR" 2>/dev/null || true
}
trap cleanup EXIT

# ── T1: mw init ────────────────────────────────────────────────────────────────
echo "=== T1: mw init ==="
python3 "$MW_PY" init --project="$TEST_DIR"
_assert "[ -f '$TEST_DIR/.agenticdoc/_index.md' ]" "VC-028: .agenticdoc/_index.md exists"
_assert "[ -f '$TEST_DIR/.pi/extensions/agent-team-loop.js' ]" "VC-028: Extension bundle installed"

# ── T2: mw serve ───────────────────────────────────────────────────────────────
echo "=== T2: mw serve start ==="
# mw-dispatch-reliability: serve fails fast when NO route has credentials
# (AC-002), so the smoke run must provide at least one. A dummy key is fine:
# the spawned pi worker just fails auth and reaches status "failed", which is
# exactly what T5's detection assertion observes.
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-smoke-dummy-key}"
python3 "$MW_PY" start \
    --project="$TEST_DIR" \
    --pi-port=17001 --claude-port=17003 &
sleep 3

PID_FILE="$TEST_DIR/.mw/mw.pid"
_assert "[ -f '$PID_FILE' ]" "VC-045: PID file exists after start"

# ── T3: duplicate mw serve rejected ───────────────────────────────────────────
echo "=== T3: duplicate serve rejected ==="
if python3 "$MW_PY" serve --project="$TEST_DIR" --pi-port=17001 --claude-port=17003 2>&1 | grep -q "already running"; then
    _pass "VC-045: duplicate serve rejected"
else
    _fail "VC-045: duplicate serve not rejected"
fi

# ── T4: proxy ports LISTENING ──────────────────────────────────────────────────
echo "=== T4: proxy ports LISTENING ==="
sleep 2
for port in 17001 17003; do
    if netstat -an 2>/dev/null | grep -q ":$port.*LISTEN"; then
        _pass "VC-021: port $port LISTENING"
    else
        _fail "VC-021: port $port not LISTENING (proxy may need real upstream)"
    fi
done

# ── T5: pending task detected ≤ 5s ────────────────────────────────────────────
echo "=== T5: pending task detection ==="
WORKERS_FILE="$TEST_DIR/.agenticdoc/_workers.parallel"
# The task must actually exist: pending entries whose task.md is missing are
# archived as stale by the launcher instead of being spawned. Worker tasks live
# under {owner}/workers/<task-key>/ (keyless ad-hoc: _scratch/workers/).
TASK_DIR="$TEST_DIR/.agenticdoc/_scratch/workers/t-smoke"
mkdir -p "$TASK_DIR"
printf 'type: coding\nsmoke detection task\n' > "$TASK_DIR/task.md"
echo "t-smoke | pending | pi |  | $TASK_DIR/task.md | $(date -u +%Y-%m-%dT%H:%M:%SZ) | $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$WORKERS_FILE"

# Wait up to 15s for the status to change to running/done/failed (poll
# interval 5s + spawn latency). NOT detecting the task is a failure — the old
# else-branch here used to pass unconditionally (false positive, AC-014).
TIMEOUT=15; DETECTED=false
for i in $(seq 1 $TIMEOUT); do
    sleep 1
    if grep -q "t-smoke | running\|t-smoke | done\|t-smoke | failed" "$WORKERS_FILE" 2>/dev/null; then
        DETECTED=true; break
    fi
done
if $DETECTED; then _pass "AC-001: pending task detected within ${i}s"
else _fail "AC-001: pending task NOT detected within ${TIMEOUT}s (check .mw/launcher.log)"; fi

# ── T6: mw serve survives pi exit ─────────────────────────────────────────────
echo "=== T6: mw serve survives pi exit ==="
MWS_PID=$(cat "$PID_FILE" 2>/dev/null || echo "")
if [ -n "$MWS_PID" ] && kill -0 "$MWS_PID" 2>/dev/null; then
    _pass "VC-046: mw serve still running after test (pi not running)"
else
    _fail "VC-046: mw serve not running"
fi

# ── T7: mw stop ───────────────────────────────────────────────────────────────
echo "=== T7: mw stop ==="
python3 "$MW_PY" stop --project="$TEST_DIR"
sleep 1
if [ ! -f "$PID_FILE" ] || ! kill -0 "$(cat "$PID_FILE" 2>/dev/null)" 2>/dev/null; then
    _pass "VC-045: PID file cleaned up after stop"
else
    _fail "VC-045: PID file still present after stop"
fi

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo "=============================="
echo "PASS: $PASS  FAIL: $FAIL"
if [ ${#ERRORS[@]} -gt 0 ]; then
    echo "Failures:"
    for e in "${ERRORS[@]}"; do echo "  - $e"; done
    echo "FAIL: smoke_test"
    exit 1
fi
echo "PASS: smoke_test"
exit 0
