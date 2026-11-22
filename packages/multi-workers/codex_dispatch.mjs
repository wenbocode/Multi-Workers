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
import { createCodexDispatchAdapter } from "../coding-agent/src/extensions/agent-team-loop/pm/codex-pm-workflow.ts";
import { AckStore } from "../coding-agent/src/extensions/agent-team-loop/shared/ack-store.ts";
import { readEnvelope } from "../coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts";
import { IndexStore } from "../coding-agent/src/extensions/agent-team-loop/shared/index-store.ts";
import { WorkerStore } from "../coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts";

const params = JSON.parse(readFileSync(0, "utf8"));
const cardType = readEnvelope(params.card_path).type;
if (cardType !== params.type || (cardType !== "coding" && !(params.workflow === "codex-lite" && cardType === "review"))) {
	throw new Error("The requested worker type must match a coding card or a Codex lightweight review card");
}
const cwd = process.cwd();
const root = path.join(cwd, ".agenticdoc");
const indexStore = new IndexStore(root);
if (params.workflow !== undefined && params.workflow !== "codex-lite") throw new Error("Unknown Codex PM workflow");
const dispatchAdapter =
	params.workflow === "codex-lite"
		? createCodexDispatchAdapter(root, indexStore, params.key, params.claim_id, cardType)
		: undefined;
const resourceLoader = new DefaultResourceLoader({
	cwd,
	agentDir: getAgentDir(),
	noExtensions: true,
	noSkills: true,
	noThemes: true,
	noContextFiles: true,
	noPromptTemplates: true,
	extensionFactories: [
		(pi) =>
			registerWorkerTools(
				pi,
				new WorkerStore(root),
				new AckStore(root),
				indexStore,
				root,
				{},
				cwd,
				undefined,
				undefined,
				dispatchAdapter,
			),
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
