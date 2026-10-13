#!/usr/bin/env bash
# Build agent-team-loop Extension bundle
# Output: dist/extensions/agent-team-loop.js (relative to packages/multi-workers/)

set -e

# esbuild is a native binary: under Git Bash/MSYS/Cygwin on Windows it needs
# Windows-style paths (H:/...), not the msys /h/... form. `pwd -W` yields the
# Windows path there; on Linux/macOS it errors, so fall back to plain `pwd`.
cd "$(dirname "$0")/../.."
REPO_ROOT="$(pwd -W 2>/dev/null || pwd)"
SRC="$REPO_ROOT/packages/coding-agent/src/extensions/agent-team-loop/index.ts"
OUT="$REPO_ROOT/packages/multi-workers/dist/extensions/agent-team-loop.js"

# C-31: inject the pi version literal into the bundle. A bundled module cannot
# resolve packages/coding-agent/package.json at runtime, so config.ts's
# `pkg.version` read would fall back to "0.0.0" and the producer identity line
# would be incomparable. Same define as mw.py::_build_bundle.
VERSION="$(node -p "require('$REPO_ROOT/packages/coding-agent/package.json').version" 2>/dev/null || true)"

mkdir -p "$(dirname "$OUT")"

node -e "
const esbuild = require('esbuild');
esbuild.build({
  entryPoints: ['$SRC'],
  bundle: true,
  outfile: '$OUT',
  platform: 'node',
  // ESM output: the host loads the bundle via jiti.import(path, {default:true}).
  // A CJS bundle's esbuild __toCommonJS/__esModule interop makes {default:true}
  // resolve to an object (not the activate fn) when the install dir has no
  // \"type\":\"module\" package.json, so the loader rejects it. Real ESM exports
  // let jiti unwrap the default reliably regardless of the install location.
  format: 'esm',
  target: 'node18',
  external: ['node:*'],
  define: { __PI_CODING_AGENT_VERSION__: '$VERSION' },
  logLevel: 'info',
}).catch(() => process.exit(1));
"

echo "Built: $OUT"

# Self-check: the host loads this bundle with jiti.import(path, {default:true})
# and rejects it unless the result is a function (see core/extensions/loader.ts).
# Load it the same way and fail the build loudly if the contract is broken —
# this catches format/interop regressions here instead of silently at runtime.
node -e "
const { createJiti } = require('jiti');
const url = require('url');
const j = createJiti(url.pathToFileURL(process.cwd() + '/').href, { moduleCache: false });
j.import('$OUT', { default: true }).then((f) => {
  if (typeof f !== 'function') {
    console.error('Self-check FAILED: host loader expects a function, got ' + typeof f + '. Extension would silently fail to load.');
    process.exit(1);
  }
  console.log('Self-check OK: default export loads as a function (' + (f.name || 'anon') + ')');
}).catch((e) => { console.error('Self-check FAILED:', e.message); process.exit(1); });
"
