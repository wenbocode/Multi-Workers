import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { configPath, gatesDir, roadmapPath } from "../../src/extensions/agent-team-loop/autopilot/status-model.ts";
import { registerAskDecisionTool } from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import { resolvePmGateRoute } from "../../src/extensions/agent-team-loop/pm/gate-route.ts";
import { createHarness, getMessageText } from "./harness.ts";

const key = "gaze-integration-spike";
const gateDp = "dp-gate-approve";
const gateId = "gate-0001";
let project: string;

function storeGate(owner: string, status = "pending") {
	const dir = gatesDir(project);
	fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(
		path.join(dir, `${gateId}.md`),
		[
			"---",
			`id: ${gateId}`,
			"kind: stage-close",
			`key: ${owner}`,
			"stage: 1",
			`status: ${status}`,
			"created_at: 2026-11-17T01:00:00Z",
			"created_by: conductor",
			"question: Close this stage?",
			"---",
		].join("\n"),
	);
}

beforeEach(() => {
	project = fs.mkdtempSync(path.join(os.tmpdir(), "mw-pm-gate-"));
});
afterEach(() => fs.rmSync(project, { recursive: true, force: true }));

describe("PM gate routing", () => {
	it("keeps an authorized B2 module build out of P0, distinguishes queue errors and preserves a real gate", async () => {
		const runner = vi.fn(async () => {
			throw new Error("Unexpected decision transport");
		});
		const h = await createHarness({
			extensionFactories: [
				(pi) => {
					registerAskDecisionTool(pi, {
						projectDir: project,
						key,
						initiatorRole: "pm",
						runner,
						lifecycleRunner: runner,
					});
				},
			],
		});
		const lookup = async (trigger: string) => {
			h.setResponses([
				fauxAssistantMessage(
					[
						fauxToolCall("ask_decision", {
							dp: gateDp,
							trigger,
							material: {
								gate_background: "Approved five-file build in CL3064387",
								current_state: "Fresh readiness passed",
								condition_evidence: [],
								pm_note: {
									subject: "B2",
									planned_action: "Build the Gaze module",
									basis: {
										goal: "Compile the module",
										evidence: "Source hashes",
										budget: "One build",
										authority: "Recorded user ruling",
									},
								},
							},
						}),
					],
					{ stopReason: "toolUse" },
				),
				fauxAssistantMessage("Read the routing result"),
			]);
			await h.session.prompt("Check the B2 gate dependency");
			const result = getMessageText(h.session.messages.filter((m) => m.role === "toolResult").at(-1));
			expect(result).not.toMatch(/blocked on decision|decision_id|"owner"|submit_offer/);
			return JSON.parse(result);
		};
		try {
			expect(await lookup("H-03YGK-B2-corrected-payload-build")).toMatchObject({
				available: false,
				gate_route: { status: "not-applicable" },
			});
			storeGate("other-key");
			expect((await lookup(gateId)).gate_route.status).toBe("not-applicable");
			storeGate(key);
			expect((await lookup("H-03YGK-B2-corrected-payload-build")).gate_route.status).toBe("not-applicable");
			expect((await lookup(gateId)).gate_route).toMatchObject({
				status: "framework-gate",
				gate_id: gateId,
				kind: "stage-close",
				blocker: "automation-inactive",
			});
			fs.writeFileSync(configPath(project), JSON.stringify({ enabled: true, auto_gate_mode: "live" }));
			expect((await lookup(gateId)).gate_route.blocker).toBe("p0-disabled");
			const control = path.join(project, ".mw");
			fs.mkdirSync(control, { recursive: true });
			const points = path.join(control, "decide-points.json");
			fs.writeFileSync(points, "{");
			expect((await lookup(gateId)).gate_route.status).toBe("state-unavailable");
			fs.writeFileSync(points, JSON.stringify({ points: { [gateDp]: { enabled: true } } }));
			expect((await lookup(gateId)).gate_route).toEqual({
				status: "framework-gate",
				gate_id: gateId,
				kind: "stage-close",
				instruction: expect.stringContaining("until that handler authorizes it"),
			});
			expect(fs.readFileSync(path.join(gatesDir(project), `${gateId}.md`), "utf8")).toContain("status: pending");
			fs.writeFileSync(path.join(gatesDir(project), `${gateId}.md`), "invalid gate");
			expect((await lookup(gateId)).gate_route.status).toBe("state-unavailable");
			expect(runner).not.toHaveBeenCalled();
		} finally {
			h.cleanup();
		}
	});

	it("matches a keyless stage gate only to a key in that stage and excludes completed gates", () => {
		storeGate("");
		expect(resolvePmGateRoute(project, key, gateId).status).toBe("state-unavailable");
		fs.writeFileSync(
			roadmapPath(project),
			[
				"## Stage 1: integration",
				"> goal: integration",
				"> status: running",
				"### Keys",
				"| key | role | depends_on |",
				"| --- | --- | --- |",
				"| gaze-integration-spike | PM | |",
			].join("\n"),
		);
		expect(resolvePmGateRoute(project, key, gateId).status).toBe("framework-gate");
		expect(resolvePmGateRoute(project, "other-key", gateId).status).toBe("not-applicable");
		storeGate(key, "rejected");
		expect(resolvePmGateRoute(project, key, gateId).status).toBe("not-applicable");
	});

	it("rechecks the live queue when dp-route suggests a gate, including a cached selection", async () => {
		const runner = vi.fn(async (request: { input: string }) => {
			const { meta } = JSON.parse(request.input);
			return {
				status: 0,
				timedOut: false,
				stderr: "",
				stdout: JSON.stringify({
					available: true,
					file_evidence: [],
					decision_id: `dp-route:${meta.logical_id}`,
					mode: "suggest",
					acted: false,
					answers: { entry: { value: gateDp }, basis_id: { value: "scope" } },
				}),
			};
		});
		const lifecycleRunner = vi.fn(async () => ({
			status: 0,
			timedOut: false,
			stderr: "",
			stdout: '{"status":"written","recorded":true}',
		}));
		const h = await createHarness({
			extensionFactories: [
				(pi) => {
					registerAskDecisionTool(pi, {
						projectDir: project,
						key,
						initiatorRole: "pm",
						runner,
						lifecycleRunner,
					});
				},
			],
		});
		try {
			for (const expected of ["not-applicable", "framework-gate"]) {
				if (expected === "framework-gate") storeGate(key);
				h.setResponses([
					fauxAssistantMessage(
						[
							fauxToolCall("ask_decision", {
								dp: "dp-route",
								trigger: gateId,
								material: {
									decision_actor: "PM",
									decision_object: "Stage closure",
									question: "Which entry applies?",
								},
								preparation: {
									prepared_at: "2026-11-17T01:00:00Z",
									basis_catalog: [
										{
											id: "scope",
											text: "Review the scope",
											material_refs: ["decision_object"],
											applies_to: [gateDp],
										},
									],
								},
							}),
						],
						{ stopReason: "toolUse" },
					),
					fauxAssistantMessage("Read the route"),
				]);
				await h.session.prompt("Resolve this decision route");
				const message = h.session.messages.filter((m) => m.role === "toolResult").at(-1);
				expect(message?.details).toMatchObject({
					available: true,
					selection: { id: gateDp },
					gate_route: { status: expected },
				});
				if (expected === "framework-gate") expect(message?.details).toHaveProperty("matter_suppressed", true);
			}
			expect(runner).toHaveBeenCalledTimes(1);
			expect(lifecycleRunner).toHaveBeenCalledTimes(1);
		} finally {
			h.cleanup();
		}
	});
});
