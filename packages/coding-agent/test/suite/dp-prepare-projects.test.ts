import { cpSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { hostname, tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { expect, it, vi } from "vitest";
import { type DecideRunner, registerAskDecisionTool } from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import type { HostFacts } from "../../src/extensions/agent-team-loop/shared/decision-handoff.ts";
import { createHarness, getMessageText } from "./harness.ts";

interface ReplayCase {
	project: string;
	missing_choices: string[];
	authored_terms: string[];
	identifiers: string[];
	wire: string;
	negative: Record<string, unknown> & { key: string };
	positive: Record<string, unknown>;
	sources: Record<string, string>;
}

interface ModelRequest {
	model: string;
	questions: { decision_selection: { criteria: Record<string, string> } };
	state: {
		evidence_sources: { included_lines: number[][]; text: string }[];
		terminology: Record<string, string>;
	};
}

const replayCases: ReplayCase[] = JSON.parse(
	readFileSync(new URL("../fixtures/dp-prepare-projects.json", import.meta.url), "utf8"),
);
const mw = fileURLToPath(new URL("../../../multi-workers/mw.py", import.meta.url));

function save(file: string, data: unknown): void {
	writeFileSync(file, `${JSON.stringify(data, null, 2)}\n`, "utf8");
}

it.each(replayCases)(
	"prepares $project once and records the same-call selection",
	async (sample) => {
		const root = mkdtempSync(join(tmpdir(), "dp-prepare-"));
		const doc = join(root, ".agenticdoc");
		const config = join(root, ".mw");
		const { key } = sample.negative;
		const project = sample.project.toLowerCase();
		const recorded = process.env.MW_DP_STEER_CAPTURE;
		const original = recorded && join(recorded, project === "bearing" ? "bearing-original" : "gaze-one-choice");
		const inputs =
			original && recorded
				? [
						JSON.parse(readFileSync(join(original, "original-tool-input.json"), "utf8")),
						JSON.parse(readFileSync(join(recorded, `${project}-narrow-files`, "replay-tool-input.json"), "utf8")),
					]
				: [sample.negative, sample.positive];
		const calls: { request: ModelRequest; raw: Record<string, unknown> }[] = [];
		let delayResponse = false;
		const server = createServer((request, response) => {
			const chunks: Buffer[] = [];
			request.on("data", (chunk: Buffer) => chunks.push(chunk));
			request.on("end", () => {
				const body: ModelRequest = JSON.parse(Buffer.concat(chunks).toString("utf8"));
				const accepted =
					request.method === "POST" &&
					request.url === "/v1/decisions" &&
					Object.hasOwn(body.questions?.decision_selection?.criteria ?? {}, sample.wire);
				const raw = accepted
					? {
							id: `dp-prepare-${project}`,
							model: body.model,
							answers: { decision_selection: { type: "choice", choice: sample.wire, confidence: 0.95 } },
						}
					: { error: "Unexpected request" };
				calls.push({ request: body, raw });
				if (delayResponse) return;
				response.writeHead(accepted ? 200 : 400, { "Content-Type": "application/json" });
				response.end(JSON.stringify(raw));
			});
		});
		await new Promise<void>((resolve, reject) => server.once("error", reject).listen(0, "127.0.0.1", resolve));
		let harness: Awaited<ReturnType<typeof createHarness>> | undefined;
		try {
			if (original) {
				cpSync(join(original, "source-files"), root, { recursive: true });
			} else {
				for (const [relative, text] of Object.entries(sample.sources)) {
					const target = join(root, relative);
					mkdirSync(dirname(target), { recursive: true });
					writeFileSync(target, text, "utf8");
				}
			}
			mkdirSync(config);
			writeFileSync(join(doc, "target.yml"), "active: single\n");
			writeFileSync(
				join(doc, "_index.parallel"),
				`| ${key} | active | EXECUTE | ${hostname()}:${process.pid} | — | Fixture | now |\n`,
			);
			save(join(config, "decide.json"), { enabled: true, api_key: "dp-prepare-loopback-only", max_retries: 0 });
			save(join(config, "decide-points.json"), {
				version: 1,
				updated_by: "human",
				updated_at: "2026-11-23T00:00:00Z",
				points: { "dp-pm-steer": { tier: "P2", enabled: true, mode: "auto", note: "Fixture" } },
			});
			vi.stubEnv("MW_PY", process.env.MW_DP_STEER_PY ?? mw);
			vi.stubEnv("TIMI_BASE_URL", `http://127.0.0.1:${(server.address() as AddressInfo).port}`);
			vi.stubEnv("NO_PROXY", "127.0.0.1");
			vi.stubEnv("PYTHONDONTWRITEBYTECODE", "1");
			vi.stubEnv("PI_WORKER_TASK", undefined);
			const hostFacts: HostFacts = {
				binding: { role: "pm", binding_version: "1", observed_at: "2026-11-23T00:00:00Z" },
			};
			const openWindow = (timeoutMs?: number, runner?: DecideRunner) =>
				createHarness({
					extensionFactories: [
						(pi) => {
							registerAskDecisionTool(pi, {
								projectDir: root,
								key,
								initiatorRole: "pm",
								hostFacts,
								timeoutMs,
								runner,
							});
						},
					],
				});
			harness = await openWindow();
			async function ask(args: Record<string, unknown>, readDetails = false) {
				const session = harness;
				if (!session) throw new Error("Window is not initialized");
				session.setResponses([
					fauxAssistantMessage([fauxToolCall("ask_decision", args)], { stopReason: "toolUse" }),
					fauxAssistantMessage("Recorded."),
				]);
				await session.session.prompt("Check the prepared steering decision.");
				const result = session.session.messages
					.filter((message) => message.role === "toolResult" && message.toolName === "ask_decision")
					.at(-1);
				if (result?.role !== "toolResult") throw new Error("No ask_decision tool result.");
				return readDetails ? result.details : JSON.parse(getMessageText(result).split("\n")[0]);
			}
			const negative = await ask(inputs[0]);
			expect(calls).toHaveLength(0);
			const positive = await ask(inputs[1]);
			expect(positive).not.toHaveProperty("next");
			expect(negative).toMatchObject({
				available: false,
				unavailable: "input-incomplete",
				input_diagnostics: { transport: "not-sent", truncated: false },
			});
			const diagnostic = negative.input_diagnostics;
			for (const name of sample.identifiers) {
				expect(diagnostic.issues).not.toContainEqual(
					expect.objectContaining({ field: `preparation.model_context.terminology.${name}` }),
				);
			}
			expect(diagnostic.issues).toEqual(
				expect.arrayContaining(
					sample.authored_terms.map((term) =>
						expect.objectContaining({
							code: "undefined-term",
							field: `preparation.model_context.terminology.${term}`,
						}),
					),
				),
			);
			const candidateGap = diagnostic.issues.find((issue: { code: string }) => issue.code === "missing-candidates");
			expect(candidateGap?.choices ?? []).toEqual(sample.missing_choices);

			expect(calls, JSON.stringify(positive)).toHaveLength(1);
			const sent = calls[0].request;
			expect(Object.keys(sent.questions)).toEqual(["decision_selection"]);
			expect(Object.keys(sent.questions.decision_selection.criteria)).toEqual([
				"narrowA",
				"splitA",
				"direct-execA",
				"escalateA",
			]);
			expect(sent.state.evidence_sources).toHaveLength(4);
			expect(
				sent.state.evidence_sources.every((source) => source.text.trim() && source.included_lines.length === 1),
			).toBe(true);
			expect(positive).toMatchObject({
				available: true,
				acted: false,
				selection: { id: sample.wire.slice(0, -1) },
				basis: { id: expect.any(String) },
				feedback: { stage: "consumed", status: "written", recorded: true },
			});
			expect(sent.questions.decision_selection.criteria[sample.wire]).toContain(positive.basis.id);
			const ledger = readFileSync(join(doc, "_autopilot", "decision-lifecycle.jsonl"), "utf8")
				.trim()
				.split("\n")
				.map((line) => JSON.parse(line));
			expect(ledger).toEqual(
				expect.arrayContaining([
					expect.objectContaining({ decision_id: positive.decision_id, kind: "request" }),
					expect.objectContaining({ decision_id: positive.decision_id, kind: "lifecycle", lifecycle: "consumed" }),
				]),
			);
			const blocked = readdirSync(join(doc, "_autopilot", "dp-blocked")).filter((name) => name.endsWith(".json"));
			expect(blocked).toHaveLength(1);
			const receipt = JSON.parse(readFileSync(join(doc, "_autopilot", "dp-blocked", blocked[0]), "utf8"));
			expect(receipt.input_diagnostics).toEqual(diagnostic);

			if (project === "gaze") {
				const revised = structuredClone(inputs[1]);
				const selector = revised.evidence_refs[0];
				const end = selector.lines.end;
				selector.lines.end = 2147483647;
				revised.material.task_goal += " Inspect XYZ.";
				const rejected = await ask(revised);
				expect(rejected).toMatchObject({
					status: "needs-repair",
					action: "repair-material",
					draft_ref: expect.any(String),
					consecutive_no_progress: 0,
					next: { owner: "pm", action: "repair-material", done_when: expect.any(String) },
				});
				const corrections: { field: string; repair_id: string }[] = rejected.issues.flatMap(
					(issue: { repairs?: { field: string; repair_id: string }[] }) => issue.repairs ?? [],
				);
				const term = corrections.find((edit) => edit.field.endsWith("terminology.XYZ"));
				const range = corrections.find((edit) => edit.field.endsWith("lines.end"));
				expect(term && range).toBeTruthy();
				const route = {
					dp: revised.dp,
					key,
					trigger: revised.trigger,
					task_key: revised.task_key,
					draft_ref: rejected.draft_ref,
				};
				const repair = await ask({
					...route,
					changes: [{ repair_id: term?.repair_id, value: "A project measurement." }],
				});
				expect(repair).toMatchObject({ status: "needs-repair", draft_ref: rejected.draft_ref });
				const fixed = await ask({
					...route,
					preview: true,
					changes: [{ repair_id: range?.repair_id, value: end }],
				});
				expect(fixed, JSON.stringify(fixed)).toMatchObject({ status: "ready", transport: "not-sent" });
				hostFacts.stop_signals = [{ kind: "parent-cancel", signal_ref: "parent" }];
				expect(await ask(route)).toMatchObject({ status: "not-authorized", fact_ref: "parent" });
				delete hostFacts.stop_signals;
				hostFacts.budget_facts = [{ scope: "task", budget_ref: "remaining-zero" }];
				expect(await ask(route)).toMatchObject({ status: "not-authorized", fact_ref: "remaining-zero" });
				delete hostFacts.budget_facts;
				hostFacts.authority_gap = { policy_ref: "release", condition: "approval withdrawn" };
				expect(await ask(route)).toMatchObject({ status: "not-authorized", fact_ref: "release" });
				delete hostFacts.authority_gap;
				const index = join(doc, "_index.parallel");
				const claim = readFileSync(index, "utf8");
				writeFileSync(index, claim.replace("| active |", "| idle |"));
				expect(await ask(route)).toMatchObject({ status: "unavailable", transport: "not-sent" });
				writeFileSync(index, claim);
				expect(calls).toHaveLength(1);
				expect(await ask(route)).toMatchObject({ available: true });
				expect(await ask(route)).toMatchObject({ available: true, matter_suppressed: true });
				harness.cleanup();
				harness = await openWindow();
				expect(await ask(route)).toMatchObject({ available: true });
				expect(calls).toHaveLength(2);
				expect(calls[1].request.state.terminology.XYZ).toBe("A project measurement.");

				harness.cleanup();
				const inconsistentValidator = vi.fn(async () => ({
					status: 0,
					stderr: "",
					timedOut: false,
					stdout: JSON.stringify({ available: false, reason: "input-incomplete", attempts: 0 }),
				}));
				harness = await openWindow(undefined, inconsistentValidator);
				expect(await ask(route)).toMatchObject({
					status: "review",
					stage: "formal-material-check",
					next: { owner: "framework-maintainer", action: "review-validator-disagreement" },
				});
				expect(inconsistentValidator).toHaveBeenCalledOnce();

				harness.cleanup();
				harness = await openWindow(4500);
				const timed = structuredClone(inputs[1]);
				timed.material.task_goal += " Confirm the final export.";
				delayResponse = true;
				const unknown = await ask(timed, true);
				expect(unknown).toMatchObject({
					unavailable: "timeout",
					next: {
						owner: "pm",
						action: "reconcile-action",
						action_ref: expect.stringMatching(/^dp-pm-steer:/),
					},
				});
				expect(calls).toHaveLength(3);
				harness.cleanup();
				harness = await openWindow();
				delayResponse = false;
				timed.material.task_goal += " Keep the original scope.";
				timed.trigger = "changed-after-timeout";
				expect(await ask(timed)).toMatchObject({
					status: "effect-unknown",
					transport: "not-sent",
					next: { action: "reconcile-action", action_ref: unknown.next.action_ref },
				});
				expect(calls).toHaveLength(3);
			}

			const output = process.env.MW_DP_STEER_OUTPUT;
			if (output) {
				mkdirSync(output, { recursive: true });
				save(join(output, `${project}.json`), { inputs, negative, positive, calls, ledger, receipt });
			}
		} finally {
			harness?.cleanup();
			vi.unstubAllEnvs();
			await new Promise<void>((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
			rmSync(root, { recursive: true, force: true });
		}
	},
	50_000,
);
