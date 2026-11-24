from pathlib import Path
import os
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
commands = [
    (root / 'packages/coding-agent', ['node', '../../node_modules/vitest/dist/cli.js', '--run', '--cache=false', 'test/extensions/agentic-scripts-plan-gate.test.ts']),
    (root / 'packages/coding-agent', ['node', '../../node_modules/vitest/dist/cli.js', '--run', '--cache=false', 'test/extensions/agent-team-loop.test.ts', '-t', 'agentic-scripts']),
    (root, [sys.executable, '-X', 'utf8', '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', 'packages/multi-workers/test_plan_closure.py', 'packages/multi-workers/test_scope_review.py']),
]
for cwd, argv in commands:
    print('cwd=' + str(cwd) + '\n' + repr(argv), flush=True)
    subprocess.run(argv, cwd=cwd, env=env, check=True)
