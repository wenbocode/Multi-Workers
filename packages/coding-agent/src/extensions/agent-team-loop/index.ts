import type { ExtensionAPI } from "../../core/extensions/types.ts";
import { pmActivate } from "./pm/pm-orchestrator.ts";
import { workerModeActivate } from "./worker/worker-mode.ts";

export async function activate(pi: ExtensionAPI): Promise<void> {
	if (process.env.PI_WORKER_TASK) {
		await workerModeActivate(pi);
	} else {
		pmActivate(pi);
	}
}

export default activate;
