// Invoke the same PM tool as a pi window, with no conversational model turn.
import { readFileSync } from "node:fs";
import path from "node:path";
import {
	createAgentSession,
	DefaultResourceLoader,
	getAgentDir,
	SessionManager,
} from "@earendil-works/pi-coding-agent";
import { registerWorkerTools } from "../coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../coding-agent/src/extensions/agent-team-loop/shared/ack-store.ts";
import { readEnvelope } from "../coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts";
import { IndexStore } from "../coding-agent/src/extensions/agent-team-loop/shared/index-store.ts";
import { WorkerStore } from "../coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts";

const params = JSON.parse(readFileSync(0, "utf8"));
if (readEnvelope(params.card_path).type !== "coding") throw new Error("A coding task card is required");
const cwd = process.cwd();
const root = path.join(cwd, ".agenticdoc");
const resourceLoader = new DefaultResourceLoader({
	cwd,
	agentDir: getAgentDir(),
	noExtensions: true,
	noSkills: true,
	noThemes: true,
	noContextFiles: true,
	noPromptTemplates: true,
	extensionFactories: [
		(pi) => registerWorkerTools(pi, new WorkerStore(root), new AckStore(root), new IndexStore(root), root, {}, cwd),
	],
});
await resourceLoader.reload();
const { session } = await createAgentSession({ cwd, resourceLoader, sessionManager: SessionManager.inMemory(cwd) });
try {
	const dispatch = session.agent.state.tools.find((tool) => tool.name === "dispatch_worker");
	if (!dispatch) throw new Error("PM dispatch_worker was not registered");
	const reply = await dispatch.execute(params.task_key, params);
	for (const item of reply.content) {
		if (item.type === "text") process.stdout.write(`${item.text}\n`);
	}
} finally {
	session.dispose();
}
