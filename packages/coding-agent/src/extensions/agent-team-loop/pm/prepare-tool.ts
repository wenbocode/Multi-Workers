import * as fs from "node:fs";
import * as path from "node:path";
import { Type } from "typebox";
import type { ExtensionAPI, ExtensionContext } from "../../../core/extensions/types.ts";
import { PROVIDER_ID_TO_PREFIX } from "../shared/dispatch-models.ts";
import { prepareDecisionMw } from "../shared/mw-runner.ts";
import { readTaskHeaderScalar } from "../shared/task-frontmatter.ts";

export const PREPARE_PROFILE = "bounded-v1";
const PREPARE_TOOL = "prepare_dp";
const ABSORB_TOOL = "absorb_dp_preparation";

export function restrictedPrepareEnvelope(taskPath: string): string | undefined {
	try {
		const envelope = fs.readFileSync(taskPath, "utf8");
		return readTaskHeaderScalar(envelope, "prepare_profile") === PREPARE_PROFILE ? envelope : undefined;
	} catch {
		return undefined;
	}
}

function modelValue(ctx: ExtensionContext): string | undefined {
	const model = ctx.model;
	const prefix = model && PROVIDER_ID_TO_PREFIX[model.provider];
	return prefix ? `${prefix}/${model.id}` : undefined;
}

function prepareResult(projectDir: string, input: object) {
	const run = prepareDecisionMw(projectDir, input);
	if (!run.ok)
		return { content: [{ type: "text" as const, text: "Preparation host unavailable." }], details: undefined };
	return { content: [{ type: "text" as const, text: run.output }], details: undefined };
}

export function registerRestrictedPrepareWorker(
	pi: ExtensionAPI,
	projectDir: string,
	taskPath: string,
	envelope: string,
): void {
	const model = readTaskHeaderScalar(envelope, "prepare_model");
	const taskDir = path.dirname(path.resolve(taskPath));
	const task = path.basename(taskDir);
	const key = path.basename(path.dirname(path.dirname(taskDir)));
	pi.registerTool({
		name: PREPARE_TOOL,
		label: "Prepare decision materials",
		description:
			"Advance the bounded preparation run in order. begin returns source handles. Read those handles, check_inputs, compose material and preparation, check_discriminability, validate, and publish that exact revision.",
		parameters: Type.Object(
			{
				action: Type.Union([
					Type.Literal("begin"),
					Type.Literal("read"),
					Type.Literal("check_inputs"),
					Type.Literal("compose"),
					Type.Literal("check_discriminability"),
					Type.Literal("validate"),
					Type.Literal("publish"),
				]),
				handle: Type.Optional(Type.String()),
				material: Type.Optional(Type.Record(Type.String(), Type.Unknown())),
				preparation: Type.Optional(Type.Record(Type.String(), Type.Unknown())),
				revision: Type.Optional(Type.String()),
			},
			{ additionalProperties: false },
		),
		executionMode: "sequential",
		execute: async (_id, params, signal, _update, ctx) =>
			signal?.aborted
				? { content: [{ type: "text", text: "Preparation was cancelled." }], details: undefined }
				: prepareResult(projectDir, { ...params, task, key, effective_model: modelValue(ctx) }),
	});
	pi.on("before_agent_start", (event) => {
		pi.setActiveTools([PREPARE_TOOL]);
		return {
			systemPrompt: `${event.systemPrompt}\n\nPrepare materials using only prepare_dp. Begin to get the approved handles. Use the validated revision to publish. Report the revision and stop. Your work does not make or execute a DP decision.`,
		};
	});
	pi.on("tool_call", (event, ctx) => {
		if (event.toolName !== PREPARE_TOOL)
			return { block: true, reason: "The preparation Worker only has the bounded prepare_dp tool." };
		if (!model || modelValue(ctx) !== model)
			return { block: true, reason: "The preparation Worker model differs from its pinned route." };
	});
}

export function registerAbsorbDecisionPreparation(pi: ExtensionAPI, projectDir: string): void {
	pi.registerTool({
		name: ABSORB_TOOL,
		label: "Absorb decision materials",
		description:
			"Accept a published preparation revision for the same decision. Verify its facts and scope yourself and record the concrete check. Returns the material and preparation for the normal decision tool.",
		parameters: Type.Object(
			{
				key: Type.String(),
				task: Type.String(),
				revision: Type.String(),
				semantic_check: Type.String({ minLength: 1, maxLength: 1200 }),
			},
			{ additionalProperties: false },
		),
		executionMode: "sequential",
		execute: async (_id, params, signal) =>
			signal?.aborted
				? { content: [{ type: "text", text: "Absorption was cancelled." }], details: undefined }
				: prepareResult(projectDir, { ...params, action: "absorb" }),
	});
	pi.on("before_agent_start", () => pi.setActiveTools([...new Set([...pi.getActiveTools(), ABSORB_TOOL])]));
}
