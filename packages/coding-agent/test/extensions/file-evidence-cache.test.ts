import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	type DecideRunRequest,
	registerAskDecisionTool,
} from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import {
	checkFileEvidence,
	type FileEvidenceDependency,
	parseFileEvidence,
} from "../../src/extensions/agent-team-loop/pm/file-evidence-cache.ts";
import type {
	PrepareOfferInput,
	SubmitDecisionHostHandle,
} from "../../src/extensions/agent-team-loop/pm/host-submit.ts";
import type { HostFacts } from "../../src/extensions/agent-team-loop/shared/decision-handoff.ts";

const temporaryRoots: string[] = [];
afterEach(() => {
	for (const root of temporaryRoots.splice(0)) {
		const resolved = path.resolve(root);
		if (resolved.startsWith(path.resolve(os.tmpdir()) + path.sep))
			fs.rmSync(resolved, { recursive: true, force: true });
	}
});

function project(): string {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-file-evidence-"));
	temporaryRoots.push(root);
	fs.mkdirSync(path.join(root, ".mw"));
	fs.writeFileSync(path.join(root, ".mw", "decide.json"), JSON.stringify({ enabled: true }));
	return root;
}

function evidence(file: string): FileEvidenceDependency {
	try {
		return {
			path: file,
			canonical_path: fs.realpathSync(file),
			sha256: createHash("sha256").update(fs.readFileSync(file)).digest("hex"),
		};
	} catch {
		return { path: file, canonical_path: null, sha256: null, status: "missing" };
	}
}

interface ToolResult {
	content: Array<{ type: "text"; text: string }>;
	details: Record<string, unknown>;
}
interface RegisteredTool {
	name: string;
	execute(id: string, params: Record<string, unknown>): Promise<ToolResult>;
}

function registeredAsk(
	root: string,
	file: string,
	hostFacts?: HostFacts,
	submitHandle?: SubmitDecisionHostHandle,
	responseFileEvidence?: unknown,
) {
	const tools = new Map<string, RegisteredTool>();
	const calls: DecideRunRequest[] = [];
	const api = {
		registerTool(tool: RegisteredTool) {
			tools.set(tool.name, tool);
		},
		on() {},
		getActiveTools() {
			return [];
		},
		setActiveTools() {},
	} as unknown as ExtensionAPI;
	registerAskDecisionTool(api, {
		projectDir: root,
		key: "file-test",
		initiatorRole: "pm",
		hostFacts,
		submitHandle,
		runner: async (request) => {
			calls.push(request);
			const envelope = JSON.parse(request.input) as { meta: { logical_id: string } };
			const exists = fs.existsSync(file);
			return {
				status: exists ? 0 : 2,
				stderr: "",
				timedOut: false,
				stdout: JSON.stringify({
					available: exists,
					dp: "dp-QG",
					logical_id: envelope.meta.logical_id,
					decision_id: `dp-QG:${envelope.meta.logical_id}`,
					mode: "auto",
					acted: false,
					answers: exists
						? { qg_verdict: { value: "fix", confidence: 0.95 }, basis_id: { value: "repair", confidence: 0.95 } }
						: null,
					reason: exists ? null : "input-incomplete",
					confidence_source: "api",
					latency_ms: 1,
					detail: exists ? "" : "file evidence preparation failed; no request sent",
					file_evidence: responseFileEvidence ?? [evidence(file)],
				}),
			};
		},
		lifecycleRunner: async () => ({
			status: 0,
			stdout: JSON.stringify({ recorded: true, status: "written" }),
			stderr: "",
			timedOut: false,
		}),
	});
	const ask = tools.get("ask_decision");
	if (ask === undefined) throw new Error("ask tool not registered");
	const params = {
		dp: "dp-QG",
		key: "file-test",
		trigger: "review",
		material: {
			review_requirements: "verify current evidence",
			review_evidence: ["report.md:1"],
			review_findings: "a repair remains",
			uncovered_scope: "runtime unverified",
		},
		preparation: {
			prepared_at: "2026-11-16T12:00:00Z",
			basis_catalog: [
				{
					id: "repair",
					text: "repair the reported defect",
					material_refs: ["review_findings"],
					applies_to: ["fix"],
				},
				{
					id: "pass-review",
					text: "all applicable checks have current evidence",
					material_refs: ["review_evidence"],
					applies_to: ["pass"],
				},
				{
					id: "reopen-contract",
					text: "the current contract requires adjudication",
					material_refs: ["review_requirements"],
					applies_to: ["reopen"],
				},
			],
		},
	};
	return { calls, invoke: () => ask.execute("call", params) };
}

describe("authorized file evidence freshness", () => {
	it("hashes actual contents, ignores mtime changes, and detects same-size edits", () => {
		const root = project();
		const file = path.join(root, "report.md");
		fs.writeFileSync(file, "old evidence\n");
		const dependency = evidence(file);
		fs.utimesSync(file, new Date(0), new Date(0));
		expect(checkFileEvidence([dependency]).changed).toBe(false);
		fs.writeFileSync(file, "new evidence\n");
		fs.utimesSync(file, new Date(0), new Date(0));
		expect(checkFileEvidence([dependency]).changed).toBe(true);
	});

	it("rejects malformed metadata without interpreting material paths", () => {
		expect(parseFileEvidence({})).toBeUndefined();
		expect(parseFileEvidence({ file_evidence: [{ path: "relative.md", sha256: "0".repeat(64) }] })).toBeNull();
		expect(parseFileEvidence({ file_evidence: [{ path: path.resolve("safe.md"), sha256: "invalid" }] })).toBeNull();
		expect(parseFileEvidence({ file_evidence: [] })).toEqual([]);
	});

	it("allows the bounded source and contract dependencies", () => {
		const file = path.resolve("safe.md");
		const dependency: FileEvidenceDependency = { path: file, canonical_path: null, sha256: null, status: "missing" };
		expect(parseFileEvidence({ file_evidence: Array.from({ length: 69 }, () => dependency) })).toHaveLength(69);
		expect(parseFileEvidence({ file_evidence: Array.from({ length: 70 }, () => dependency) })).toBeNull();
	});

	it("exact-file policy changes invalidate cached decisions and resume the runner once", async () => {
		const root = project();
		const file = path.join(root, "report.md");
		const policy = path.join(root, ".mw", "decision-evidence.yml");
		fs.writeFileSync(file, "proof\n");
		fs.writeFileSync(policy, "read_files: [report.md]\n");
		const tool = registeredAsk(root, file, undefined, undefined, [evidence(file), evidence(policy)]);
		expect((await tool.invoke()).details.available).toBe(true);
		expect((await tool.invoke()).details.matter_suppressed).toBe(true);
		expect(tool.calls).toHaveLength(1);
		fs.writeFileSync(policy, "read_files: []\n");
		expect((await tool.invoke()).details.matter_suppressed).toBeUndefined();
		expect(tool.calls).toHaveLength(2);
	});

	it("detects missing-to-created dependencies without reading newly authorized contents", () => {
		const root = project();
		const file = path.join(root, "report.md");
		const dependency = evidence(file);
		expect(checkFileEvidence([dependency]).changed).toBe(false);
		fs.writeFileSync(file, "new proof\n");
		expect(checkFileEvidence([dependency]).changed).toBe(true);
	});

	it("retargeted aliases are invalidated before content reads", () => {
		const root = project();
		const oldTarget = path.join(root, "old.md");
		const newTarget = path.join(root, "new.md");
		const alias = path.join(root, "alias.md");
		fs.writeFileSync(oldTarget, "old\n");
		fs.writeFileSync(newTarget, "new\n");
		const dependency: FileEvidenceDependency = {
			path: alias,
			canonical_path: oldTarget,
			sha256: evidence(oldTarget).sha256,
		};
		// An ordinary file at the old alias path also differs from the expected
		// canonical target, so this does not need Windows symlink privileges.
		fs.writeFileSync(alias, "new target must not be read\n");
		expect(checkFileEvidence([dependency]).changed).toBe(true);
	});

	it("binary, removed, and oversized replacement evidence invalidate old results", () => {
		const root = project();
		const file = path.join(root, "report.md");
		fs.writeFileSync(file, "valid text\n");
		const dependency = evidence(file);
		fs.writeFileSync(file, Buffer.from([0, 255, 0]));
		expect(checkFileEvidence([dependency]).changed).toBe(true);
		fs.truncateSync(file, 8 * 1024 * 1024 + 1);
		expect(checkFileEvidence([dependency]).changed).toBe(true);
		fs.unlinkSync(file);
		expect(checkFileEvidence([dependency]).changed).toBe(true);
	});
});

describe("registered ask cache uses framework file dependencies", () => {
	it("malformed framework dependency metadata refuses success and is cached without another runner", async () => {
		const root = project();
		const file = path.join(root, "report.md");
		fs.writeFileSync(file, "proof\n");
		const handle: SubmitDecisionHostHandle = {
			prepareOffer() {
				throw new Error("invalid metadata must never prepare an offer");
			},
			readCommittedSelection() {
				return undefined;
			},
			hostExpectedFor() {
				return undefined;
			},
		};
		const tool = registeredAsk(root, file, undefined, handle, [{ path: "relative.md", sha256: "bad" }]);
		const first = await tool.invoke();
		expect(first.details.available).toBe(false);
		expect(first.details.unavailable).toBe("bad-response");
		expect(first.details.submit_offer).toMatchObject({ submittable: false, gaps: ["file-evidence-metadata"] });
		const replay = await tool.invoke();
		expect(replay.details.available).toBe(false);
		expect(replay.details.matter_suppressed).toBe(true);
		expect(replay.details.submit_offer).toMatchObject({ submittable: false, gaps: ["file-evidence-metadata"] });
		expect(tool.calls).toHaveLength(1);
	});
	it("unchanged evidence replays without a new runner; content change versions feedback and invokes once", async () => {
		const root = project();
		const file = path.join(root, "report.md");
		fs.writeFileSync(file, "old proof\n");
		const tool = registeredAsk(root, file);
		const first = await tool.invoke();
		expect(first.details.available).toBe(true);
		const replay = await tool.invoke();
		expect(replay.details.matter_suppressed).toBe(true);
		expect(tool.calls).toHaveLength(1);
		fs.writeFileSync(file, "new proof\n");
		const revised = await tool.invoke();
		expect(revised.details.available).toBe(true);
		expect(revised.details.matter_suppressed).toBeUndefined();
		expect(tool.calls).toHaveLength(2);
		const firstFeedback = first.details.decision_feedback as { matter_ref: string };
		const revisedFeedback = revised.details.decision_feedback as { matter_ref: string };
		expect(revisedFeedback.matter_ref).not.toBe(firstFeedback.matter_ref);
		await tool.invoke();
		expect(tool.calls).toHaveLength(2);
	});

	it("a repaired missing file refreshes once while unchanged missing evidence stays cached", async () => {
		const root = project();
		const file = path.join(root, "report.md");
		const tool = registeredAsk(root, file);
		expect((await tool.invoke()).details.available).toBe(false);
		expect((await tool.invoke()).details.matter_suppressed).toBe(true);
		expect(tool.calls).toHaveLength(1);
		fs.writeFileSync(file, "proof arrived\n");
		expect((await tool.invoke()).details.available).toBe(true);
		expect(tool.calls).toHaveLength(2);
	});

	it("source changes invalidate old host offer revalidation and version the next offer", async () => {
		const root = project();
		const file = path.join(root, "report.md");
		fs.writeFileSync(file, "old proof\n");
		const offers: PrepareOfferInput[] = [];
		const handle: SubmitDecisionHostHandle = {
			prepareOffer(input) {
				offers.push(input);
				return {
					prepared: false,
					metadata: { submittable: false, submit_tool: "submit_decision_handoff", gaps: [] },
				};
			},
			readCommittedSelection() {
				return undefined;
			},
			hostExpectedFor() {
				return undefined;
			},
		};
		const tool = registeredAsk(root, file, undefined, handle);
		await tool.invoke();
		const initial = offers[0].revalidate().configSignature;
		fs.writeFileSync(file, "new proof\n");
		expect(offers[0].revalidate().configSignature).not.toBe(initial);
		await tool.invoke();
		expect(offers[1].matterRef).not.toBe(offers[0].matterRef);
	});

	it("a trusted stop still prevents any new runner after an evidence change", async () => {
		const root = project();
		const file = path.join(root, "report.md");
		fs.writeFileSync(file, "old proof\n");
		const hostFacts: HostFacts = {
			binding: { role: "pm", binding_version: "file-evidence-test", observed_at: "2026-11-16T12:00:00Z" },
			stop_signals: [],
		};
		const tool = registeredAsk(root, file, hostFacts);
		await tool.invoke();
		fs.writeFileSync(file, "new proof\n");
		hostFacts.stop_signals?.push({ kind: "user-stop", signal_ref: "stop:host" });
		expect((await tool.invoke()).details.available).toBe(false);
		expect(tool.calls).toHaveLength(1);
	});
});
