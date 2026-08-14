#!/usr/bin/env bash
# Build agent-team-loop Extension bundle
# Output: dist/extensions/agent-team-loop.js (relative to packages/multi-workers/)

set -e

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$REPO_ROOT/packages/coding-agent/src/extensions/agent-team-loop/index.ts"
OUT="$REPO_ROOT/packages/multi-workers/dist/extensions/agent-team-loop.js"

mkdir -p "$(dirname "$OUT")"

node -e "
const esbuild = require('esbuild');
esbuild.build({
  entryPoints: ['$SRC'],
  bundle: true,
  outfile: '$OUT',
  platform: 'node',
  format: 'cjs',
  target: 'node18',
  external: ['node:*'],
  logLevel: 'info',
}).catch(() => process.exit(1));
"

echo "Built: $OUT"
