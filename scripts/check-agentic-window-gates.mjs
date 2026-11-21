/** Release smoke test against explicitly selected project installations. Run with Node 24+. */
import {spawnSync} from "node:child_process";
import path from "node:path";
import {inspectPlanGate} from "../packages/coding-agent/src/extensions/agent-team-loop/shared/agentic-scripts.ts";
import {PYTHON_EXE} from "../packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts";

// Exercise the loaded gate on an empty disposable key. Never advance a project phase.
const probe = `
import pathlib, sys, tempfile
directory = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(directory))
import advance_phase, plan_closure
for module in (advance_phase, plan_closure):
    if pathlib.Path(module.__file__).resolve().parent != directory:
        raise RuntimeError(f"unexpected script origin: {module.__file__}")
with tempfile.TemporaryDirectory() as workspace:
    passed, failures = advance_phase.check_gate(pathlib.Path(workspace), "tasks")
    if passed or not any("PLAN CLOSURE:" in failure for failure in failures):
        raise RuntimeError("installed gate did not reject the missing plan")
print(advance_phase.__file__, plan_closure.__file__, sep=" -> ")
`;
const projects=process.argv.slice(2);
if (!projects.length) {
	console.error("Usage: node scripts/check-agentic-window-gates.mjs <project> [project...]");
	process.exitCode=2;
}
for (const project of projects) {
	const installation=inspectPlanGate(path.resolve(project));
	if (!installation.ok) {
		console.error(installation.output);
		process.exitCode=1;
		continue;
	}
	const result=spawnSync(PYTHON_EXE,["-I","-B","-X","utf8","-c",probe,path.dirname(installation.output)],{encoding:"utf8",timeout:10000,windowsHide:true});
	if(result.status!==0){
		console.error(installation.output,result.error?.message ?? result.stderr);
		process.exitCode=1;
	} else console.log(result.stdout.trim());
}
