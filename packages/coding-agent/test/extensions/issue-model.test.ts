/**
 * T-01 (mw-issue-feedback) — dedicated tests for the pure scene/progress model.
 *
 * Model-level coverage (L1): VC-001 scene readable + provenance, VC-002
 * redaction / confirmation gate, VC-004 latest dev progress + project-only
 * listing, VC-005 local effectiveness fail-closed. Store-level L2 assertions
 * (authority record counts, offline retry, worker write rejection) belong to
 * T-03/T-06 and are NOT claimed here; see the worker report.
 *
 * No real provider, no network, no project files are read by the product
 * module; this test file reads ONLY the product source for the purity check.
 */

import * as fs from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type {
	DevUpdate,
	IssueCard,
	IssueDraft,
	LocalEvidence,
	PrepareOptions,
} from "../../src/extensions/agent-team-loop/shared/issue-model.ts";
import {
	appendDevUpdate,
	appendReporterReply,
	canonicalPayload,
	confirmIssue,
	DEV_STATUSES,
	evaluateLocalEffective,
	isInstant,
	latestDevState,
	listIssuesForProject,
	NOT_VERIFIED_PHRASE,
	observedObservation,
	parseVersion,
	pendingQuestion,
	prepareIssue,
	projectForUser,
	REDACTION_MARK,
	redactSecrets,
	renderForUser,
	summarizeForList,
	UNKNOWN,
	unknownObservation,
	userObservation,
	VERIFIED_PHRASE,
	withQuestionIdentities,
} from "../../src/extensions/agent-team-loop/shared/issue-model.ts";

// ── Fixtures (synthetic, no real project data) ────────────────────────────────

const OCCURRED = "2026-11-12T14:02:11+08:00";
const SUBMITTED = "2026-11-12T21:10:00+08:00";
const OBSERVED_AT = "2026-11-12T21:09:58+08:00";
const T1 = "2026-11-12T22:00:00+08:00";
const T2 = "2026-11-12T23:00:00+08:00";
const T3 = "2026-11-13T09:00:00+08:00";
const T4 = "2026-11-13T10:00:00+08:00";
const T5 = "2026-11-13T11:00:00+08:00";

const SECRET_A = "SENTINEL-APIKEY-9f3a2b7c";
const SECRET_B = "SUPERSECRET-VALUE-42";
const UNCONFIRMED = "UNCONFIRMED-RAW-SENTINEL-77";
const LONG_STEP = `1. 运行 /mw status 观察 serve 行；2. 重启；3. 再查询 ${"step-".repeat(120)} END-OF-REPRO-STEPS`;
const LONG_ERROR = `ERROR serve-stale: ${"E".repeat(500)} END-OF-KEY-ERROR`;
// Opaque in-memory stand-in for the authority dev_update event sha256: the pure
// model has no hash chain, so pendingQuestion fixtures attach this identity via
// withQuestionIdentities and the reply names it in inReplyTo.
const QUESTION_EVENT_HASH = "a".repeat(64);

function baseDraft(): IssueDraft {
	return {
		id: "fb-model-fixture-0001",
		title: "/mw status 重启后显示旧 serve",
		projectLabel: "project-A",
		component: unknownObservation(),
		occurredAt: userObservation(OCCURRED, SUBMITTED),
		trigger: userObservation("执行 /mw status 后重启 serve"),
		precondition: userObservation("serve 已运行超过一小时"),
		expected: userObservation("显示当前 serve 的 PID 与启动时间"),
		actual: userObservation("仍显示上一次启动的旧 PID"),
		impact: userObservation("误判 serve 未重启，卡住排障"),
		reproductionSteps: userObservation(LONG_STEP),
		reproductionFrequency: "偶发",
		errorExcerpt: userObservation(`${LONG_ERROR} Bearer ${SECRET_B}`),
		environmentAtFailure: {
			mwVersion: userObservation("0.12.2", OCCURRED),
			piVersion: unknownObservation(),
			platform: userObservation("Windows 11"),
			windowType: userObservation("tui"),
		},
		observedEnvironment: {
			mwVersion: observedObservation("0.12.4", OBSERVED_AT),
			piVersion: unknownObservation(),
			platform: observedObservation("Windows 11", OBSERVED_AT),
			windowType: unknownObservation(),
			bundleStatus: observedObservation("fresh", OBSERVED_AT),
			serveStatus: observedObservation("stale", OBSERVED_AT),
		},
		diagnosticCandidates: [
			{ id: "f1", kind: "error", text: `E123: api_key=${SECRET_A} 原始报错` },
			{ id: "f2", kind: "log", text: "用户选择的最小日志行 23:09:58" },
			{ id: "f3", kind: "log", text: `${UNCONFIRMED} 整段会话原文（未选择）` },
		],
		selectedFragmentIds: ["f1", "f2"],
	};
}

function baseOptions(): PrepareOptions {
	return { submittedAt: SUBMITTED, environmentObservedAt: OBSERVED_AT, knownSecrets: [SECRET_A, SECRET_B] };
}

function sectionBody(text: string, headingPrefix: string): string {
	return text.split(/\n## /).find((part) => part.startsWith(headingPrefix)) ?? "";
}

function deepFreeze<T>(value: T): T {
	if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
		Object.freeze(value);
		for (const key of Object.keys(value)) deepFreeze((value as unknown as Record<string, unknown>)[key]);
	}
	return value;
}

function update(at: string, fields: Partial<DevUpdate> & Pick<DevUpdate, "status">): DevUpdate {
	return {
		at,
		by: "mw-dev",
		status: fields.status,
		statusNote: fields.statusNote ?? "按现场分诊",
		nextAction: fields.nextAction ?? null,
		fixCommit: fields.fixCommit ?? null,
		releaseVersion: fields.releaseVersion ?? null,
		questionToReporter: fields.questionToReporter ?? null,
	};
}

// ── Vocabulary + helpers ──────────────────────────────────────────────────────

describe("time / version / redaction primitives", () => {
	it("accepts only tz-aware instants; naive or invalid times are unknown", () => {
		expect(isInstant(OCCURRED)).toBe(true);
		expect(isInstant("2026-11-12T14:02:11Z")).toBe(true);
		expect(isInstant("2026-11-12 14:02:11")).toBe(false);
		expect(isInstant("2026-11-12T14:02:11")).toBe(false);
		expect(isInstant("2026-13-45T14:02:11+08:00")).toBe(false);
		expect(isInstant("unknown")).toBe(false);
		expect(isInstant(null)).toBe(false);
	});

	it("parses comparable versions and rejects unknown/0.0.0 sentinels", () => {
		expect(parseVersion("0.12.5")).toEqual({ major: 0, minor: 12, patch: 5 });
		expect(parseVersion("v1.2.3-rc1")).toEqual({ major: 1, minor: 2, patch: 3 });
		expect(parseVersion("0.0.0")).toBeNull();
		expect(parseVersion("unknown")).toBeNull();
		expect(parseVersion(null)).toBeNull();
		expect(parseVersion("0.12")).toBeNull();
	});

	it("scrubs known credentials and high-confidence token shapes", () => {
		const raw = `api_key=${SECRET_A} Bearer ${SECRET_B} sk-abcdefghijklmnopqrstuvwxyz AKIA0000000000000000 password=hunter2`;
		const result = redactSecrets(raw, [SECRET_A, SECRET_B]);
		expect(result.text).not.toContain(SECRET_A);
		expect(result.text).not.toContain(SECRET_B);
		expect(result.text).not.toContain("sk-abcdefghijklmnopqrstuvwxyz");
		expect(result.text).not.toContain("AKIA0000000000000000");
		expect(result.text).not.toContain("hunter2");
		expect(result.text).toContain(`api_key=${REDACTION_MARK}`);
		expect(result.redactions).toBeGreaterThanOrEqual(5);
		expect(redactSecrets("普通报错：serve 未重启", []).text).toBe("普通报错：serve 未重启");
	});

	it("the product module is pure logic: no fs/net/env/clock/IO imports", () => {
		const sourcePath = fileURLToPath(
			new URL("../../src/extensions/agent-team-loop/shared/issue-model.ts", import.meta.url),
		);
		const source = fs.readFileSync(sourcePath, "utf8");
		expect(source).not.toMatch(/from\s+["']node:(fs|net|http|https|child_process|os|path)["']/);
		expect(source).not.toMatch(/require\(\s*["']node:(fs|net|http|https|child_process)/);
		expect(source).not.toContain("process.env");
		expect(source).not.toContain("Date.now(");
		expect(source).not.toContain("readFile");
		expect(source).not.toContain("fetch(");
		expect(source).not.toContain("await import(");
		expect(source).toContain('import { createHash } from "node:crypto"');
	});
});

// ── VC-001: scene readable, provenance, full preview ──────────────────────────

describe("VC-001(model): structured scene and full redacted preview", () => {
	it("keeps the same ID, every scene fact and the three distinct times", () => {
		const draft = baseDraft();
		const prep = prepareIssue(draft, baseOptions());
		const card = prep.card;
		expect(card.id).toBe(draft.id);
		expect(card.schema).toBe(1);
		expect(card.occurredAt).toEqual({ value: OCCURRED, source: "user", at: SUBMITTED });
		expect(card.submittedAt).toEqual({ value: SUBMITTED, source: "observed", at: SUBMITTED });
		expect(card.environmentObservedAt).toEqual({ value: OBSERVED_AT, source: "observed", at: OBSERVED_AT });
		expect(card.scene.trigger.value).toBe("执行 /mw status 后重启 serve");
		expect(card.scene.expected.value).toBe("显示当前 serve 的 PID 与启动时间");
		expect(card.scene.actual.value).toBe("仍显示上一次启动的旧 PID");
		expect(card.scene.reproductionSteps.value).toBe(LONG_STEP);
		expect(card.scene.reproductionFrequency).toBe("偶发");
		expect(card.scene.errorExcerpt.value).toContain(LONG_ERROR);
		expect(card.devTimeline).toEqual([]);
		expect(card.reporterReplies).toEqual([]);
		console.log("[VERIFY] VC-001(model): id=same scene=readable candidate-card=1");
	});

	it("the preview is COMPLETE (no truncation) and shows source/time tags", () => {
		const prep = prepareIssue(baseDraft(), baseOptions());
		expect(prep.preview).toContain(LONG_STEP);
		expect(prep.preview).toContain(LONG_ERROR);
		expect(prep.preview).toContain("故障时环境（用户陈述/未知；不得由当前实测替换）");
		expect(prep.preview).toContain(`窗口实测 @ ${OBSERVED_AT}`);
		expect(prep.preview).toContain("[用户陈述");
		expect(prep.preview).toContain("诊断片段（仅用户选择、已脱敏");
		expect(prep.preview).toContain("用户选择的最小日志行 23:09:58");
		expect(prep.preview).toContain("开发进展/反馈（开发侧解释与推测，与报障事实分栏）");
		expect(prep.preview).toContain("确认前仅保存在内存");
		// No summary/truncation markers for the verbatim key text.
		expect(prep.preview).not.toContain("…");
		expect(prep.preview.length).toBeGreaterThan(LONG_STEP.length + LONG_ERROR.length);
	});

	it("current measurement never replaces the failure-time snapshot", () => {
		const prep = prepareIssue(baseDraft(), baseOptions());
		expect(prep.card.scene.environmentAtFailure.mwVersion.value).toBe("0.12.2");
		expect(prep.card.scene.environmentAtFailure.mwVersion.source).toBe("user");
		expect(prep.card.scene.observedEnvironment.mwVersion.value).toBe("0.12.4");
		expect(prep.card.scene.observedEnvironment.mwVersion.source).toBe("observed");
		const text = renderForUser(prep.card, {
			localVersion: "0.12.1",
			bundleStale: false,
			serveStale: false,
			entrypointInstalled: true,
			collectedAt: T5,
		});
		expect(sectionBody(text, "故障时环境")).toContain("0.12.2");
		expect(sectionBody(text, "故障时环境")).not.toContain("0.12.4");
		expect(sectionBody(text, "窗口实测环境")).toContain("0.12.4");
		expect(sectionBody(text, "窗口实测环境")).toContain(`窗口实测 @ ${OBSERVED_AT}`);
		expect(sectionBody(text, "窗口实测环境")).toContain("不代表故障时快照");
	});

	it("refuses an observed value in the failure-time environment", () => {
		const draft = baseDraft();
		draft.environmentAtFailure.mwVersion = observedObservation("0.12.4", OBSERVED_AT);
		const prep = prepareIssue(draft, baseOptions());
		expect(prep.card.scene.environmentAtFailure.mwVersion.value).toBeNull();
		expect(prep.card.scene.environmentAtFailure.mwVersion.source).toBe("unknown");
		expect(prep.notes.some((note) => note.includes("不适用于该字段"))).toBe(true);
		expect(prep.card.scene.observedEnvironment.mwVersion.value).toBe("0.12.4");
	});

	it("is deterministic and does not mutate or persist the frozen draft", () => {
		const draft = deepFreeze(baseDraft());
		const options = deepFreeze(baseOptions());
		const first = prepareIssue(draft, options);
		const second = prepareIssue(draft, options);
		expect(first.previewSha256).toBe(second.previewSha256);
		expect(first.submissionDigest).toBe(second.submissionDigest);
		expect(first.submissionDigest).toMatch(/^[0-9a-f]{16}$/);
		expect(first.previewSha256).toMatch(/^[0-9a-f]{64}$/);
		expect(draft.diagnosticCandidates[2].text).toContain(UNCONFIRMED);
		expect(first.card.diagnostics).toHaveLength(2);
		console.log(`[VERIFY] VC-001(model): deterministic digest=${first.submissionDigest}`);
	});
});

// ── VC-002: redaction + confirmation ─────────────────────────────────────────

describe("VC-002(model): no leak, no unconfirmed fragment, refusal = no payload", () => {
	it("known credentials and unconfirmed raw input never enter the payload or preview", () => {
		const prep = prepareIssue(baseDraft(), baseOptions());
		const payload = canonicalPayload(prep.card);
		const surfaces = [payload, prep.preview, prep.notes.join("\n")];
		for (const surface of surfaces) {
			expect(surface).not.toContain(SECRET_A);
			expect(surface).not.toContain(SECRET_B);
			expect(surface).not.toContain(UNCONFIRMED);
		}
		expect(payload).toContain(REDACTION_MARK);
		expect(prep.redactions).toBeGreaterThan(0);
		expect(prep.card.diagnostics.map((f) => f.id)).toEqual(["f1", "f2"]);
		expect(prep.card.diagnostics.every((f) => f.source === "user")).toBe(true);
		expect(prep.notes.some((note) => note.includes("未选择的诊断片段仅保留在内存"))).toBe(true);
	});

	it("confirmIssue is the only producer of an approved payload; refusal yields null", () => {
		const prep = prepareIssue(baseDraft(), baseOptions());
		expect(confirmIssue(prep, { confirmed: false, confirmedAt: T1, previewSha256: prep.previewSha256 })).toBeNull();
		expect(
			confirmIssue(prep, { confirmed: true, confirmedAt: "2026-11-12", previewSha256: prep.previewSha256 }),
		).toBeNull();
		expect(confirmIssue(prep, { confirmed: true, confirmedAt: null, previewSha256: prep.previewSha256 })).toBeNull();
		expect(confirmIssue(prep, { confirmed: true, confirmedAt: T1, previewSha256: "0".repeat(64) })).toBeNull();
		expect(
			confirmIssue(
				{ ...prep, preview: "tampered" },
				{ confirmed: true, confirmedAt: T1, previewSha256: prep.previewSha256 },
			),
		).toBeNull();
		const approved = confirmIssue(prep, { confirmed: true, confirmedAt: T1, previewSha256: prep.previewSha256 });
		expect(approved?.approvedForPersistence).toBe(true);
		expect(approved?.confirmedAt).toBe(T1);
		expect(approved?.card).toBe(prep.card);
		expect(canonicalPayload(approved?.card ?? prep.card)).not.toContain(SECRET_A);
		console.log("[VERIFY] VC-002(model): created=0 (on refusal) leaked=0");
	});
});

// ── VC-004: development progress, fix/version separation, project-only list ───

describe("VC-004(model): latest progress, separate fix/version, own-project listing", () => {
	function progressed(): IssueCard {
		let card = prepareIssue(baseDraft(), baseOptions()).card;
		card = appendDevUpdate(
			card,
			update(T1, { status: "待分诊", statusNote: "现场完整，待复现", nextAction: "复现 serve 重启" }),
		);
		card = appendDevUpdate(
			card,
			update(T2, { status: "修复中", statusNote: "定位到状态缓存", questionToReporter: "请补充重启后的原始报错" }),
		);
		card = appendDevUpdate(
			card,
			update(T3, { status: "已修复", statusNote: "已修正状态读取", fixCommit: "abc1234" }),
		);
		card = appendDevUpdate(
			card,
			update(T4, {
				status: "已发布",
				statusNote: "随 0.12.5 发布",
				releaseVersion: "0.12.5",
				questionToReporter: "请确认升级后是否复现",
			}),
		);
		return card;
	}

	it("folds the timeline: latest status, fix commit and release version kept separate", () => {
		const card = progressed();
		const state = latestDevState(card);
		expect(state.status).toBe("已发布");
		expect(state.fixCommit).toBe("abc1234");
		expect(state.releaseVersion).toBe("0.12.5");
		expect(state.updatedAt).toBe(T4);
		expect(state.statusNote).toBe("随 0.12.5 发布");
		expect(state.questionToReporter).toBe("请确认升级后是否复现");
		expect(pendingQuestion(card)).toBe("请确认升级后是否复现");
		expect(DEV_STATUSES).toEqual(["待分诊", "修复中", "已修复", "已发布"]);
		const text = renderForUser(card, {
			localVersion: "0.12.1",
			bundleStale: false,
			serveStale: false,
			entrypointInstalled: true,
			collectedAt: T5,
		});
		expect(text).toContain("- 修复提交: abc1234");
		expect(text).toContain("- 发布版本: 0.12.5");
		expect(text).toContain("修复提交: abc1234；发布版本: 0.12.5（分开显示）");
		expect(summarizeForList(card)).toEqual({
			id: "fb-model-fixture-0001",
			title: "/mw status 重启后显示旧 serve",
			status: "已发布",
			updatedAt: T4,
			needsReply: true,
		});
		console.log("[VERIFY] VC-004(model): latest=已发布 fix_commit=abc1234 release_version=0.12.5");
	});

	it("appends are pure, never overwrite the scene, and redact dev/reply text", () => {
		const original = prepareIssue(baseDraft(), baseOptions()).card;
		const withUpdate = appendDevUpdate(
			original,
			update(T2, { status: "修复中", statusNote: `使用 ${SECRET_A} 调试`, questionToReporter: "请补充原始报错" }),
			[SECRET_A, SECRET_B],
		);
		expect(original.devTimeline).toHaveLength(0);
		expect(withUpdate.devTimeline).toHaveLength(1);
		expect(withUpdate.scene.actual.value).toBe("仍显示上一次启动的旧 PID");
		expect(canonicalPayload(withUpdate)).not.toContain(SECRET_A);
		// R05: a reply clears a question by STABLE EVENT IDENTITY, not by a late
		// clock. The fixture now names the question's event hash in inReplyTo and
		// the cards inspected by pendingQuestion carry that identity projection.
		const replied = appendReporterReply(
			withUpdate,
			{ at: T5, text: `补充现场，口令 ${SECRET_B}`, source: "user", inReplyTo: QUESTION_EVENT_HASH },
			[SECRET_A, SECRET_B],
		);
		expect(replied.reporterReplies).toHaveLength(1);
		expect(canonicalPayload(replied)).not.toContain(SECRET_B);
		const identified = withQuestionIdentities(withUpdate, [QUESTION_EVENT_HASH]);
		const identifiedReplied = withQuestionIdentities(replied, [QUESTION_EVENT_HASH]);
		expect(pendingQuestion(identified)).toBe("请补充原始报错");
		expect(pendingQuestion(identifiedReplied)).toBeNull();
		expect(summarizeForList(identifiedReplied).needsReply).toBe(false);
		expect(() => appendDevUpdate(original, update("2026-11-12", { status: "待分诊" }))).toThrow();
		expect(() => appendReporterReply(original, { at: T5, text: "x", source: "user", inReplyTo: null })).not.toThrow();
	});

	it("a no-ID list shows ONLY the current project's rows (foreign=0)", () => {
		const own = progressed();
		const foreignDraft = baseDraft();
		foreignDraft.id = "fb-model-fixture-foreign";
		foreignDraft.projectLabel = "project-B";
		const foreign = prepareIssue(foreignDraft, baseOptions()).card;
		const rows = listIssuesForProject([own, foreign], "project-A");
		expect(rows).toHaveLength(1);
		expect(rows[0].id).toBe("fb-model-fixture-0001");
		expect(rows[0].status).toBe("已发布");
		expect(listIssuesForProject([own, foreign], "project-B")[0].id).toBe("fb-model-fixture-foreign");
		expect(listIssuesForProject([own, foreign], "project-C")).toEqual([]);
		console.log("[VERIFY] VC-004(model): foreign=0 own=1 latest=已发布");
	});
});

// ── VC-005: local effectiveness fail-closed ──────────────────────────────────

describe("VC-005(model): development fix is never local effectiveness", () => {
	function fixedCard(withVersion: boolean): IssueCard {
		let card = prepareIssue(baseDraft(), baseOptions()).card;
		card = appendDevUpdate(
			card,
			update(T3, { status: "已修复", statusNote: "已修正状态读取", fixCommit: "abc1234" }),
		);
		if (withVersion) {
			card = appendDevUpdate(card, update(T4, { status: "已发布", releaseVersion: "0.12.5" }));
		}
		return card;
	}

	const good: LocalEvidence = {
		localVersion: "0.12.5",
		bundleStale: false,
		serveStale: false,
		entrypointInstalled: true,
		collectedAt: T5,
	};

	it("insufficient or older local evidence always reads 本项目未验证已用上修复", () => {
		const card = fixedCard(true);
		const cases: Array<[string, LocalEvidence]> = [
			["旧版本", { ...good, localVersion: "0.12.1" }],
			["bundle 陈旧", { ...good, bundleStale: true }],
			["serve 陈旧", { ...good, serveStale: true }],
			["入口未安装", { ...good, entrypointInstalled: false }],
			["版本未知", { ...good, localVersion: null }],
			["版本不可比", { ...good, localVersion: "unknown" }],
			["陈旧状态未知", { ...good, bundleStale: null }],
			["采集时间未知", { ...good, collectedAt: null }],
			["不同主版本", { ...good, localVersion: "1.0.0" }],
		];
		for (const [name, evidence] of cases) {
			const result = evaluateLocalEffective(card, evidence);
			expect(result.state, name).not.toBe("verified");
			expect(result.phrase, name).toBe(NOT_VERIFIED_PHRASE);
			const text = renderForUser(card, evidence);
			expect(text, name).toContain(NOT_VERIFIED_PHRASE);
			expect(text, name).not.toContain(VERIFIED_PHRASE);
		}
		const noVersion = evaluateLocalEffective(fixedCard(false), good);
		expect(noVersion.state).toBe("unknown");
		expect(noVersion.phrase).toBe(NOT_VERIFIED_PHRASE);
		const noFix = evaluateLocalEffective(prepareIssue(baseDraft(), baseOptions()).card, good);
		expect(noFix.state).toBe("unknown");
		expect(noFix.phrase).toBe(NOT_VERIFIED_PHRASE);
		console.log("[VERIFY] VC-005(model): local_effective=not-verified verified-claim=0 cases=11");
	});

	it("a bare 已修复 status with a registered version is still not locally verified", () => {
		const card = appendDevUpdate(
			prepareIssue(baseDraft(), baseOptions()).card,
			update(T3, { status: "已修复", fixCommit: "abc1234", releaseVersion: "0.12.5" }),
		);
		const older = { ...good, localVersion: "0.12.1" };
		const result = evaluateLocalEffective(card, older);
		expect(result.state).toBe("not-verified");
		expect(result.phrase).toBe(NOT_VERIFIED_PHRASE);
		expect(renderForUser(card, older)).toContain("开发侧状态: 已修复（仅权威记录）");
		expect(renderForUser(card, older)).toContain(NOT_VERIFIED_PHRASE);
		expect(renderForUser(card, older)).not.toContain(VERIFIED_PHRASE);
	});

	it("fail-closed: same version + clean flags is NOT verified without an identity chain", () => {
		const card = fixedCard(true);
		const result = evaluateLocalEffective(card, good);
		expect(result.state).not.toBe("verified");
		expect(result.state).toBe("not-verified");
		expect(result.phrase).toBe(NOT_VERIFIED_PHRASE);
		// Explicit reason and version hint are retained (first phase).
		expect(result.reason).toContain("0.12.5");
		expect(result.reason).toContain("不足以证明");
		const text = renderForUser(card, good);
		expect(text).toContain(NOT_VERIFIED_PHRASE);
		expect(text).not.toContain(VERIFIED_PHRASE);
		// Development-side status is still shown as authoritative-record only.
		expect(renderForUser(card, { ...good, localVersion: "0.12.1" })).toContain("仅权威记录");
	});

	// ── T-08A regression: version + freshness is NOT identity proof ──────────
	// `good` is the maximal first-phase evidence: the local version EQUALS the
	// fix version (0.12.5), bundle/serve are not stale, the entrypoint is
	// installed and collection time is legal — but there is still NO verifiable
	// fix-artifact -> installed-artifact -> running-process identity chain (no
	// artifact digest, no loaded-module fingerprint). This is the "same version
	// but different code / missing running fingerprint" case AC-005 forbids
	// reporting as verified.
	it("same version but different code (stale bundle/serve) is NOT verified", () => {
		const card = fixedCard(true);
		for (const evidence of [
			{ ...good, bundleStale: true },
			{ ...good, serveStale: true },
		]) {
			const result = evaluateLocalEffective(card, evidence);
			expect(result.state).not.toBe("verified");
			expect(result.phrase).toBe(NOT_VERIFIED_PHRASE);
			expect(renderForUser(card, evidence)).not.toContain(VERIFIED_PHRASE);
		}
	});

	it("an older version stays not-verified, with an explicit reason", () => {
		const older = { ...good, localVersion: "0.12.1" };
		const result = evaluateLocalEffective(fixedCard(true), older);
		expect(result.state).toBe("not-verified");
		expect(result.phrase).toBe(NOT_VERIFIED_PHRASE);
		expect(result.reason).toContain("低于修复版本");
		expect(renderForUser(fixedCard(true), older)).not.toContain(VERIFIED_PHRASE);
	});

	it("NO first-phase evidence combination yields verified / VERIFIED_PHRASE", () => {
		const versions: Array<string | null> = [
			null,
			"unknown",
			"0.0.0",
			"0.12.1",
			"0.12.4",
			"0.12.5",
			"0.12.6",
			"v0.13.0",
			"1.0.0",
		];
		const flags: Array<boolean | null> = [true, false, null];
		const card = fixedCard(true);
		let checked = 0;
		for (const localVersion of versions) {
			for (const bundleStale of flags) {
				for (const serveStale of flags) {
					for (const entrypointInstalled of flags) {
						const evidence: LocalEvidence = {
							localVersion,
							bundleStale,
							serveStale,
							entrypointInstalled,
							collectedAt: T5,
						};
						const result = evaluateLocalEffective(card, evidence);
						expect(result.state).not.toBe("verified");
						expect(result.phrase).toBe(NOT_VERIFIED_PHRASE);
						checked++;
					}
				}
			}
		}
		console.log(`[VERIFY] VC-005(T-08A): verified-claim=0 combos=${checked}`);
	});
});

// ── Missing-value semantics ──────────────────────────────────────────────────

describe("missing values are explicit unknown, never fabricated", () => {
	function sparseDraft(): IssueDraft {
		const draft = baseDraft();
		draft.component = unknownObservation();
		draft.occurredAt = unknownObservation();
		draft.trigger = unknownObservation();
		draft.precondition = unknownObservation();
		draft.expected = unknownObservation();
		draft.actual = unknownObservation();
		draft.impact = unknownObservation();
		draft.reproductionSteps = unknownObservation();
		draft.reproductionFrequency = null;
		draft.errorExcerpt = unknownObservation();
		draft.environmentAtFailure = {
			mwVersion: unknownObservation(),
			piVersion: unknownObservation(),
			platform: unknownObservation(),
			windowType: unknownObservation(),
		};
		draft.observedEnvironment = {
			mwVersion: observedObservation("0.12.4", null), // no capture time -> unknown
			piVersion: unknownObservation(),
			platform: unknownObservation(),
			windowType: unknownObservation(),
			bundleStatus: unknownObservation(),
			serveStatus: unknownObservation(),
		};
		draft.diagnosticCandidates = [];
		draft.selectedFragmentIds = [];
		return draft;
	}

	it("unknown is rendered explicitly; an observed value without a time is dropped", () => {
		const prep = prepareIssue(sparseDraft(), baseOptions());
		expect(prep.card.scene.reproductionFrequency).toBe("未知");
		expect(prep.card.scene.observedEnvironment.mwVersion.value).toBeNull();
		expect(prep.notes.some((note) => note.includes("缺合法采集时间"))).toBe(true);
		expect(prep.card.occurredAt.value).toBeNull();
		expect(prep.card.occurredAt.source).toBe("unknown");
		expect(prep.preview).toContain(`- 复现频率: ${UNKNOWN}`);
		expect(prep.preview).toContain(`- 触发操作: ${UNKNOWN}`);
		expect(prep.preview).toContain("待分诊（未定位）");
		expect(prep.preview).toContain("复现步骤（未知时明确标注，不编造）");
		expect(prep.preview).not.toContain("0.12.4");
		const projection = projectForUser(prep.card, {
			localVersion: null,
			bundleStale: null,
			serveStale: null,
			entrypointInstalled: null,
			collectedAt: null,
		});
		expect(projection.facts.every((fact) => fact.value === UNKNOWN || fact.label.includes("时间"))).toBe(true);
		expect(projection.localEffective.state).toBe("unknown");
		console.log(`[VERIFY] VC-001(model): unknown=${UNKNOWN} explicit guessed=0`);
	});

	it("prints a compact synthetic projection sample for review", () => {
		const draft = baseDraft();
		draft.reproductionSteps = userObservation("1. 重启 serve；2. 再执行 /mw status（偶发）");
		draft.errorExcerpt = userObservation("ERROR: stale serve PID @ 14:02:11");
		draft.diagnosticCandidates = [{ id: "f1", kind: "error", text: "ERROR: stale serve PID @ 14:02:11" }];
		draft.selectedFragmentIds = ["f1"];
		const prep = prepareIssue(draft, baseOptions());
		const confirmed = confirmIssue(prep, { confirmed: true, confirmedAt: T1, previewSha256: prep.previewSha256 });
		expect(confirmed?.approvedForPersistence).toBe(true);
		let card = appendDevUpdate(
			prep.card,
			update(T3, { status: "已修复", fixCommit: "abc1234", releaseVersion: "0.12.5" }),
		);
		card = appendDevUpdate(
			card,
			update(T4, { status: "已发布", statusNote: "随 0.12.5 发布", nextAction: "等待本项目升级核对" }),
		);
		const text = renderForUser(card, {
			localVersion: "0.12.2",
			bundleStale: true,
			serveStale: false,
			entrypointInstalled: true,
			collectedAt: T5,
		});
		expect(text).toContain(NOT_VERIFIED_PHRASE);
		console.log(`\n[SAMPLE] 用户可读投影（合成数据）\n${text}`);
	});

	it("invalid window times become unknown with a note, never a fabricated instant", () => {
		const prep = prepareIssue(baseDraft(), {
			...baseOptions(),
			submittedAt: "2026-11-12 21:10:00",
			environmentObservedAt: null,
		});
		expect(prep.card.submittedAt.value).toBeNull();
		expect(prep.card.environmentObservedAt.value).toBeNull();
		expect(prep.notes.filter((note) => note.includes("窗口未提供合法带时区时间"))).toHaveLength(2);
		expect(prep.card.occurredAt.value).toBe(OCCURRED); // failure time unaffected
	});
});
