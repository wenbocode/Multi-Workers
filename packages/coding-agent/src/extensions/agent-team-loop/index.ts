import type { ExtensionAPI } from "../../core/extensions/types.ts";
import { pmActivate } from "./pm/pm-orchestrator.ts";
import { workerModeActivate } from "./worker/worker-mode.ts";

// Defense against a double-load: if the same bundle is loaded twice in one host
// process (e.g. a global install AND a stale project-local copy), registering the
// tools twice makes the host reject the second load with a hard "tool conflicts"
// error and pi fails to start. A process-global guard makes the second activate()
// a no-op instead, so pi always comes up. mw init also removes redundant local
// copies (global-wins), but this keeps a rogue duplicate from ever crashing pi.
const ACTIVATION_FLAG = "__agentTeamLoopActivated";

export async function activate(pi: ExtensionAPI): Promise<void> {
	const g = globalThis as Record<string, unknown>;
	if (g[ACTIVATION_FLAG]) {
		return;
	}
	g[ACTIVATION_FLAG] = true;

	if (process.env.PI_WORKER_TASK) {
		await workerModeActivate(pi);
	} else {
		pmActivate(pi);
	}
}

export default activate;
