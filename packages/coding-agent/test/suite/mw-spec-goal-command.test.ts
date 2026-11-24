import * as fs from "node:fs";
import { tmpdir } from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage } from "@earendil-works/pi-ai";
import { afterEach, expect, it, vi } from "vitest";
import type { ExtensionUIContext } from "../../src/core/extensions/types.ts";
import { registerSpecGoalCommand } from "../../src/extensions/agent-team-loop/pm/spec-goal-command.ts";
import { windowClaimId } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { appendKeyGoal } from "../../src/extensions/agent-team-loop/shared/key-goal.ts";
import { createHarness, type Harness } from "./harness.ts";

const specification =
	"---\r\nversion: 1\r\n---\r\n\r\n# Old spec\r\n\r\n## Acceptance\r\n\r\n| AC-001 | Check the report. |\r\n";
const goal =
	"Goal ID: alpha/GOAL-01\n目标: Produce an Alpha report aligned with the project.\n" +
	"范围边界: Report authoring only. Dashboards belong to a separate key.\n停止条件: Readers can verify the report.";
const roots: string[] = [];
const harnesses: Harness[] = [];

afterEach(() => {
	for (const harness of harnesses.splice(0)) harness.cleanup();
	for (const root of roots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
});

async function setup(spec = specification, claim = windowClaimId()) {
	const project = fs.mkdtempSync(path.join(tmpdir(), "mw-spec-goal-command-"));
	roots.push(project);
	const docs = path.join(project, ".agenticdoc");
	const file = path.join(docs, "alpha", "spec.md");
	fs.mkdirSync(path.dirname(file), { recursive: true });
	fs.writeFileSync(file, spec);
	fs.writeFileSync(path.join(docs, "goal.md"), "## Goal\nDeliver clearer reports.\n");
	const index = new IndexStore(docs);
	const setClaim = (claimId: string) =>
		index.upsert({ key: "alpha", status: "active", phase: "IMPLEMENT", claimId, deps: "", desc: "", updated: "" });
	await setClaim(claim);
	const harness = await createHarness({ extensionFactories: [(pi) => registerSpecGoalCommand(pi, project)] });
	harnesses.push(harness);
	const editor = vi.fn(async (_title: string, _prefill?: string): Promise<string | undefined> => goal);
	const confirm = vi.fn(async () => true);
	const notify = vi.fn();
	await harness.session.bindExtensions({
		uiContext: { editor, confirm, notify } as unknown as ExtensionUIContext,
		mode: "tui",
	});
	const generate = vi.fn(() => fauxAssistantMessage("Draft from the selected model."));
	harness.setResponses([
		(context) => {
			expect(context.systemPrompt).toContain("Goal ID: <key>/GOAL-01");
			expect(context.systemPrompt).toContain("停止条件:");
			expect(context.tools ?? []).toHaveLength(0);
			expect(context.messages).toHaveLength(1);
			expect(context.messages[0]).toMatchObject({
				role: "user",
				content: JSON.stringify({
					key: "alpha",
					specification: spec,
					project_goal: "## Goal\nDeliver clearer reports.\n",
				}),
			});
			return generate();
		},
	]);
	return { file, docs, harness, editor, confirm, notify, setClaim, generate };
}

it("uses the current model once and writes the edited and confirmed goal into a legacy spec", async () => {
	const { file, docs, harness, editor, confirm, generate } = await setup();
	await harness.session.prompt("/mw-spec-goal");
	expect(generate).toHaveBeenCalledTimes(1);
	expect(editor).toHaveBeenCalledWith("编辑 alpha 的 spec_goal", "Draft from the selected model.");
	expect(confirm).toHaveBeenCalledWith("写入 alpha 的 spec_goal？", goal);
	expect(harness.session.messages).toEqual([]);
	const updated = fs.readFileSync(file, "utf8");
	expect(
		updated.replace(
			`\r\n## §0 Goal Alignment\r\n\r\n### spec_goal\r\n\r\n${goal.replace(/\n/g, "\r\n")}\r\n\r\n`,
			"",
		),
	).toBe(specification);
	expect(appendKeyGoal("", docs, "alpha")).toBe(`## [mw] Current key goal (alpha)\n\n${goal}`);
	await harness.session.prompt("/mw-spec-goal");
	expect(generate).toHaveBeenCalledTimes(1);
	expect(editor).toHaveBeenCalledTimes(1);
	expect(fs.readFileSync(file, "utf8")).toBe(updated);
});

it.each([true, false])("preserves the alignment text with an existing empty goal heading (%s)", async (hasHeading) => {
	const template =
		"# Spec\n\n## §0 Goal Alignment\n\nOriginal alignment text.\n\n" +
		(hasHeading ? "### spec_goal\n\n<!-- Pending -->\n\n" : "") +
		"### Constraints\nKeep output.\n";
	const { file, docs, harness } = await setup(template);
	await harness.session.prompt("/mw-spec-goal");
	const updated = fs.readFileSync(file, "utf8");
	expect(updated.match(/### spec_goal/g)).toHaveLength(1);
	expect(updated.replace(`\n${hasHeading ? "" : "### spec_goal\n\n"}${goal}\n\n`, "")).toBe(template);
	expect(appendKeyGoal("", docs, "alpha")).toBe(`## [mw] Current key goal (alpha)\n\n${goal}`);
});

it.each(["saved", "missing", "unowned"])("shows the %s goal without drafting or writing", async (state) => {
	const saved = `# Spec\n\n## §0 Goal Alignment\n\n### spec_goal\n\n${goal}\n`;
	const spec = state === "missing" ? specification : saved;
	const { file, harness, editor, confirm, notify, generate } = await setup(
		spec,
		state === "unowned" ? "some-other-window:9" : windowClaimId(),
	);
	await harness.session.prompt("/mw-spec-goal show");
	if (state === "saved") {
		expect(notify).toHaveBeenCalledWith(`## [mw] Current key goal (alpha)\n\n${goal}`, "info");
	} else if (state === "missing") {
		expect(notify).toHaveBeenCalledWith("alpha 尚未填写 spec_goal。", "warning");
	} else {
		expect(notify).toHaveBeenCalledWith("请先在本窗口认领一个进行中的 SDD key。", "error");
	}
	expect(generate).not.toHaveBeenCalled();
	expect(editor).not.toHaveBeenCalled();
	expect(confirm).not.toHaveBeenCalled();
	expect(fs.readFileSync(file, "utf8")).toBe(spec);
});

it.each(["cancel editing", "decline save", "spec changed", "claim switched", "unowned", "model failed"])(
	"leaves the spec intact when %s",
	async (condition) => {
		const { file, harness, editor, confirm, setClaim, generate } = await setup(
			specification,
			condition === "unowned" ? "some-other-window:9" : windowClaimId(),
		);
		const changed = `${specification}\r\nUpdated by PM.\r\n`;
		switch (condition) {
			case "cancel editing":
				editor.mockResolvedValue(undefined);
				break;
			case "decline save":
				confirm.mockResolvedValue(false);
				break;
			case "spec changed":
				confirm.mockImplementation(async () => {
					fs.writeFileSync(file, changed);
					return true;
				});
				break;
			case "claim switched":
				confirm.mockImplementation(async () => {
					await setClaim("some-other-window:9");
					return true;
				});
				break;
			case "model failed":
				harness.setResponses([fauxAssistantMessage("", { stopReason: "error" })]);
				break;
		}
		await harness.session.prompt("/mw-spec-goal");
		expect(fs.readFileSync(file, "utf8")).toBe(condition === "spec changed" ? changed : specification);
		if (condition === "unowned" || condition === "model failed") {
			expect(generate).not.toHaveBeenCalled();
			expect(editor).not.toHaveBeenCalled();
		}
	},
);
