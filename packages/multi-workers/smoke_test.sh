#!/usr/bin/env bash
# smoke_test.sh — E2E Level 2 verification for agent-team-loop
# Run in Git Bash on Windows. Requires: python3, node, netstat, tasklist
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

_pid_alive() {
    # Git Bash's kill -0 cannot see DETACHED_PROCESS (mw start detaches the
    # serve process), so fall back to tasklist on Windows.
    [ -n "$1" ] || return 1
    kill -0 "$1" 2>/dev/null && return 0
    tasklist //FI "PID eq $1" 2>/dev/null | grep -q "$1"
}

# ── Cleanup ────────────────────────────────────────────────────────────────────
cleanup() {
    python3 "$MW_PY" stop --project="$TEST_DIR" 2>/dev/null || true
    rm -rf "$TEST_DIR" 2>/dev/null || true
}
trap cleanup EXIT

# ── T1: mw init ────────────────────────────────────────────────────────────────
echo "=== T1: mw init ==="
INIT_OUT="$(python3 "$MW_PY" init --project="$TEST_DIR")"
printf '%s\n' "$INIT_OUT"
_assert "[ -f '$TEST_DIR/.agenticdoc/_index.md' ]" "VC-028: .agenticdoc/_index.md exists"
# AC-036: global install wins — mw init only copies the bundle project-locally
# when no global install exists (~/.pi/agent/extensions/). Assert whichever
# install path init actually took.
GLOBAL_EXT="$(printf '%s\n' "$INIT_OUT" | sed -n 's/.*Using global extension install: //p')"
if [ -n "$GLOBAL_EXT" ]; then
    if command -v cygpath >/dev/null 2>&1; then
        GLOBAL_EXT="$(cygpath -u "$GLOBAL_EXT")"
    fi
    _assert "[ -f '$GLOBAL_EXT' ]" "VC-028: Extension bundle installed (global)"
elif printf '%s\n' "$INIT_OUT" | grep -q "Removed redundant project-local extension"; then
    _assert "[ -f '$HOME/.pi/agent/extensions/agent-team-loop.js' ]" "VC-028: Extension bundle installed (global)"
else
    _assert "[ -f '$TEST_DIR/.pi/extensions/agent-team-loop.js' ]" "VC-028: Extension bundle installed (project-local)"
fi

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
# Capture output + exit code separately: `set -o pipefail` makes the original
# `cmd | grep -q` pipeline fail on the rejection's exit 1 even when grep
# matched. timeout guards the (product-broken) case where the duplicate check
# passes and a second serve would run forever.
T3_RC=0
T3_OUT="$(timeout 10 python3 "$MW_PY" serve --project="$TEST_DIR" --pi-port=17001 --claude-port=17003 2>&1)" || T3_RC=$?
if [ "$T3_RC" -ne 0 ] && printf '%s\n' "$T3_OUT" | grep -q "already running"; then
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
# The queue row's task_path is consumed by the Windows Python launcher: it
# must be a Windows-style path. MSYS converts argv, not file content, so a
# POSIX /tmp/... path here would resolve against the launcher's cwd drive and
# look like a missing task.md (archived as stale).
TASK_PATH="$TASK_DIR/task.md"
if command -v cygpath >/dev/null 2>&1; then
    TASK_PATH="$(cygpath -w "$TASK_PATH")"
fi
echo "t-smoke | pending | pi |  | $TASK_PATH | $(date -u +%Y-%m-%dT%H:%M:%SZ) | $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$WORKERS_FILE"

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
if _pid_alive "$MWS_PID"; then
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
