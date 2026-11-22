/**
 * pm/issue-command.ts — T-04 of key `mw-issue-feedback`: the pi-window side of
 * `/mw issue report|retry|status|update|reply|bind`.
 *
 * This module owns the guided scene form, the FULL redacted preview, the real
 * UI confirmation, the same-ID dev progress / supplement-question / reporter
 * reply flow, the reporter-facing status projection and the explicit dev-root
 * bind confirmation. It consumes the frozen T-01 model, T-02 root locator and
 * T-03 store; it does NOT fork their schema, state vocabulary, redaction,
 * preview, idempotency, lock or root-discovery logic.
 *
 * Hard rules:
 *  - A shared write happens ONLY after `ui.confirm(title, FULL_PREVIEW)` returns
 *    exactly `true`. Cancellation, timeout, an undefined answer, a thrown
 *    dialog, a missing UI, an untrusted/unauthorized window or a refused actor
 *    leave BOTH the authority and the project's local index untouched.
 *  - Actor trust facts (role / trustedWindow / writeAuthorized / roots / by /
 *    label) come from the injected HOST (T-05 supplies real window facts) and
 *    are NEVER parsed from command arguments or defaulted to `true`. The store
 *    independently re-checks `PI_WORKER_TASK` because production uses
 *    `createIssueCommandStore()` without an env override.
 *  - `knownSecrets` is only the caller-supplied transient list. report /
 *    update / reply redact with that SAME list BEFORE the preview is rendered
 *    and pass the SAME list to the store. No auth/env scan, no log/source read,
 *    no automatic upload, no Python CLI, no cwd/root guessing.
 *  - `status.pendingQuestion` (not the last dev update's `text` line) is the
 *    latest supplement question still lacking a reply and is rendered
 *    explicitly. Development progress and reporter replies are appended under
 *    the same ID; the original scene / verbatim error text is never replaced.
 *  - Local effectiveness stays first-phase fail-closed: development
 *    "已修复/已发布" is never rendered as "本项目已验证已用上修复".
 *
 * T-05 wiring: `handleIssueCommand(args, { host, ui, store })` with
 * `store = createIssueCommandStore(projectDir)` and a `ui` adapter built from
 * the real `ExtensionCommandContext` (`ctx.ui` + `ctx.hasUI`). See the exported
 * contracts below for every host fact T-05 must prove.
 */

import {
	type Confirmation,
	DEV_STATUSES,
	type DevStateView,
	type DevStatus,
	type DiagnosticCandidate,
	type IssueDraft,
	isInstant,
	type LocalEffectiveResult,
	type LocalEvidence,
	NOT_VERIFIED_PHRASE,
	type Observation,
	type ObservedEnvironmentFacts,
	observedObservation,
	prepareIssue,
	REDACTION_MARK,
	REPRODUCTION_FREQUENCIES,
	type ReproductionFrequency,
	redactSecrets,
	UNKNOWN,
	unknownObservation,
	userObservation,
	VERIFIED_PHRASE,
} from "../shared/issue-model.ts";
import {
	type BindIssueDevRootOptions,
	type BindIssueDevRootResult,
	bindIssueDevRoot,
	formatIssueDevRootFailure,
	type IssueDevRootFailure,
} from "../shared/issue-root.ts";
import {
	ISSUE_STORE_ENTRY_ONLY_NOTICE,
	type IssueActorRole,
	type IssueIncomingListRequest,
	type IssueIncomingListResult,
	type IssueIncomingReadRequest,
	type IssueIncomingReadResult,
	type IssueListRequest,
	type IssueListResult,
	type IssueMutationResult,
	type IssueProgressFields,
	type IssueProgressRequest,
	type IssueReplyFields,
	type IssueReplyRequest,
	type IssueRetryRequest,
	type IssueStatusRequest,
	type IssueStatusResult,
	IssueStore,
	type IssueStoreActor,
	IssueStoreError,
	type IssueStoreListRow,
	type IssueSubmitRequest,
	type IssueSubmitResult,
	isIssueId,
	issueTextSha256,
	newIssueId,
	renderDevUpdatePreview,
	renderReporterReplyPreview,
} from "../shared/issue-store.ts";
import {
	escapeIssueIdentity,
	escapeUntrustedText,
	type IssueTextMode,
	normalizeIssueText,
} from "../shared/issue-text.ts";

// ── Injected host / UI / store contracts (T-05 consumes this surface) ───────

export const ISSUE_SUBCOMMANDS = ["report", "retry", "status", "inbox", "update", "reply", "bind"] as const;
export type IssueSubcommand = (typeof ISSUE_SUBCOMMANDS)[number];

export interface IssueUIDialogOptions {
	readonly timeout?: number;
	readonly signal?: AbortSignal;
}

/** Narrow, fakeable view of `ctx.ui`. `hasUI` comes from `ExtensionContext`;
 * `confirm/input/editor/select/notify` map 1:1 to `ExtensionUIContext`.
 * `present` is an optional full-text surface (T-05 can use `ctx.ui.custom()`
 * or `ctx.ui.notify()`); when omitted, `notify` receives the COMPLETE text.
 * Nothing here is ever truncated: the exact same string is also passed as the
 * `message` of the real `confirm` dialog. */
export interface IssueCommandUI {
	readonly hasUI: boolean;
	confirm(title: string, message: string, opts?: IssueUIDialogOptions): Promise<boolean>;
	input(title: string, placeholder?: string, opts?: IssueUIDialogOptions): Promise<string | undefined>;
	editor(title: string, prefill?: string, opts?: IssueUIDialogOptions): Promise<string | undefined>;
	select(title: string, options: readonly string[], opts?: IssueUIDialogOptions): Promise<string | undefined>;
	notify(message: string, type?: "info" | "warning" | "error"): void;
	present?(title: string, text: string): void | Promise<void>;
}

/** Host-measured environment values. `observedAt` must be a real tz-aware
 * capture instant; without it every value stays unknown. The window does NOT
 * read versions/bundle/serve itself here — T-05 must supply observed facts. */
export interface IssueWindowEnvironment {
	readonly observedAt: string | null;
	readonly values: Partial<Record<keyof ObservedEnvironmentFacts, string>>;
}

/** Host facts T-05 MUST supply from the real pi window (never from args):
 *  - `projectRoot`: canonical current-project root; `devRoot`: canonical MW dev
 *    repo root for dev-scope update/bind; `pointerFile`: EXPLICIT pointer path
 *    for bind (no implicit machine-config write).
 *  - `role`, `trustedWindow`, `writeAuthorized`: real PM-window identity and
 *    authorization. No field defaults to `true`; absent/false is a refusal.
 *  - `projectLabel` (non-sensitive), `by` (window actor label).
 *  - `knownSecrets`: only transient caller-provided credential values.
 *  - `localEvidence`: real installed version / bundle / serve / entrypoint
 *    facts plus collection time; `null` means explicit unknown (fail-closed).
 *  - `observedEnvironment`: real window observations + capture instant.
 *  - `now`: window clock returning a tz-aware ISO instant. */
export interface IssueCommandHost {
	readonly projectRoot: string;
	readonly projectLabel: string;
	readonly by: string;
	readonly role: IssueActorRole;
	readonly trustedWindow: boolean;
	readonly writeAuthorized: boolean;
	readonly devRoot: string | null;
	readonly pointerFile: string | null;
	readonly knownSecrets: readonly string[];
	readonly localEvidence: LocalEvidence | null;
	readonly observedEnvironment: IssueWindowEnvironment | null;
	readonly now: () => string;
}

/** Structural subset of the real `IssueStore`. Production passes
 * `createIssueCommandStore()`; offline tests pass a real store with a temp
 * pointer or a spy for pure boundary checks. */
export interface IssueCommandStore {
	submit(request: IssueSubmitRequest): Promise<IssueSubmitResult> | IssueSubmitResult;
	retry(request: IssueRetryRequest): Promise<IssueSubmitResult> | IssueSubmitResult;
	status(request: IssueStatusRequest): IssueStatusResult | Promise<IssueStatusResult>;
	list(request: IssueListRequest): IssueListResult | Promise<IssueListResult>;
	appendProgress(request: IssueProgressRequest): Promise<IssueMutationResult> | IssueMutationResult;
	reply(request: IssueReplyRequest): Promise<IssueMutationResult> | IssueMutationResult;
	/** Dev-authority inbox reads (T-09B). Required, never optional: a store
	 * double must delegate or refuse explicitly, so no old interface silently
	 * turns a dev read into a project status/list read. */
	listIncoming(request: IssueIncomingListRequest): IssueIncomingListResult | Promise<IssueIncomingListResult>;
	readIncoming(request: IssueIncomingReadRequest): IssueIncomingReadResult | Promise<IssueIncomingReadResult>;
}

export interface IssueCommandDeps {
	readonly host: IssueCommandHost;
	readonly ui: IssueCommandUI;
	readonly store: IssueCommandStore;
	/** Injectable for offline bind tests; defaults to the real T-02 binder. */
	readonly bindRoot?: (options: BindIssueDevRootOptions) => BindIssueDevRootResult;
	/** Injectable ID generator; defaults to the store's `newIssueId()`. */
	readonly newId?: () => string;
}

/** Production store wiring. Deliberately passes NO `env`: the store reads
 * `PI_WORKER_TASK` itself, so a worker cannot self-promote via actor fields. */
export function createIssueCommandStore(projectRoot: string): IssueCommandStore {
	return new IssueStore({ projectRoot });
}

export interface IssueCommandResult {
	readonly ok: boolean;
	readonly sub: IssueSubcommand | "unknown";
	readonly code: string;
	readonly message: string;
	/** Complete user-facing text shown via `ui.present`/`ui.notify`. */
	readonly text: string;
	readonly id: string | null;
	readonly display: string | null;
	/** Exact FULL redacted preview the user confirmed (never a summary). */
	readonly preview: string | null;
	readonly previewSha256: string | null;
	readonly pendingQuestion: string | null;
	readonly development: DevStateView | null;
	readonly localEffective: LocalEffectiveResult | null;
	readonly rows: readonly IssueStoreListRow[];
	readonly refused: boolean;
	readonly confirmed: boolean | null;
	/** Store/pointer write methods actually invoked (empty on every refusal). */
	readonly writesAttempted: readonly string[];
	readonly notes: readonly string[];
	readonly rootFailure: IssueDevRootFailure | null;
}

interface ResultInput extends Partial<IssueCommandResult> {
	readonly sub: IssueSubcommand | "unknown";
	readonly code: string;
	readonly message: string;
	readonly text: string;
}

function makeResult(input: ResultInput): IssueCommandResult {
	return {
		ok: input.ok ?? false,
		sub: input.sub,
		code: input.code,
		message: input.message,
		text: input.text,
		id: input.id ?? null,
		display: input.display ?? null,
		preview: input.preview ?? null,
		previewSha256: input.previewSha256 ?? null,
		pendingQuestion: input.pendingQuestion ?? null,
		development: input.development ?? null,
		localEffective: input.localEffective ?? null,
		rows: input.rows ?? [],
		refused: input.refused ?? false,
		confirmed: input.confirmed ?? null,
		writesAttempted: input.writesAttempted ?? [],
		notes: input.notes ?? [],
		rootFailure: input.rootFailure ?? null,
	};
}

function refused(sub: IssueSubcommand | "unknown", code: string, message: string): IssueCommandResult {
	return makeResult({
		sub,
		code,
		message,
		text: `# /mw issue ${sub} — 拒绝\n- ${message}\n- 未执行任何写入。`,
		refused: true,
	});
}

// ── Command argument parsing: closed field sets, no host-fact injection ─────

export interface IssueCommandArgs {
	readonly sub: IssueSubcommand | null;
	readonly id: string | null;
	readonly fields: ReadonlyMap<string, string>;
	readonly error: string | null;
}

const REPORT_FIELDS: ReadonlySet<string> = new Set<string>([
	"title",
	"component",
	"occurredAt",
	"trigger",
	"precondition",
	"expected",
	"actual",
	"impact",
	"steps",
	"frequency",
	"error",
	"mwVersion",
	"piVersion",
	"platform",
	"windowType",
	"diagnostic",
	"diagnosticKind",
	"candidate",
]);
const UPDATE_FIELDS: ReadonlySet<string> = new Set<string>([
	"status",
	"statusNote",
	"nextAction",
	"fixCommit",
	"releaseVersion",
	"question",
]);
const REPLY_FIELDS: ReadonlySet<string> = new Set<string>(["text", "inReplyTo"]);
const HOST_ONLY_FIELDS: ReadonlySet<string> = new Set<string>([
	"role",
	"scope",
	"actor",
	"trustedWindow",
	"writeAuthorized",
	"projectRoot",
	"devRoot",
	"pointerFile",
	"projectLabel",
	"by",
	"knownSecrets",
	"localEvidence",
	"env",
]);
const WRITE_SUBCOMMANDS: ReadonlySet<IssueSubcommand> = new Set<IssueSubcommand>([
	"report",
	"retry",
	"update",
	"reply",
	"bind",
]);

/** Whitespace outside quotes splits; quotes let a value contain spaces and
 * newlines. A token is `key=value` unless it is the positional feedback ID.
 * No shell interpretation, no flag parsing, no host-fact parameters. */
function tokenizeArgs(text: string): string[] {
	const tokens: string[] = [];
	let current = "";
	let quote: '"' | "'" | null = null;
	let started = false;
	for (const char of text) {
		if (quote !== null) {
			if (char === quote) quote = null;
			else current += char;
			continue;
		}
		if (char === '"' || char === "'") {
			quote = char;
			started = true;
			continue;
		}
		if (/\s/.test(char)) {
			if (started) {
				tokens.push(current);
				current = "";
				started = false;
			}
			continue;
		}
		current += char;
		started = true;
	}
	if (started) tokens.push(current);
	return tokens;
}

function allowedFields(sub: IssueSubcommand): ReadonlySet<string> {
	if (sub === "report") return REPORT_FIELDS;
	if (sub === "update") return UPDATE_FIELDS;
	if (sub === "reply") return REPLY_FIELDS;
	return new Set<string>();
}

function badArgs(sub: IssueSubcommand | null, error: string): IssueCommandArgs {
	return { sub, id: null, fields: new Map<string, string>(), error };
}

export function parseIssueCommandArgs(raw: string): IssueCommandArgs {
	const tokens = tokenizeArgs(raw.trim());
	if (tokens.length > 0 && tokens[0] === "issue") tokens.shift();
	const subToken = tokens.shift() ?? "";
	const sub = ISSUE_SUBCOMMANDS.includes(subToken as IssueSubcommand) ? (subToken as IssueSubcommand) : null;
	if (sub === null) {
		return badArgs(null, `未知 issue 子命令；可用: ${ISSUE_SUBCOMMANDS.join("|")}`);
	}
	const fields = new Map<string, string>();
	let id: string | null = null;
	for (const token of tokens) {
		const equals = token.indexOf("=");
		if (equals < 0) {
			const acceptsId =
				sub === "retry" || sub === "status" || sub === "inbox" || sub === "update" || sub === "reply";
			if (acceptsId && id === null) {
				id = token;
				continue;
			}
			return badArgs(sub, `多余位置参数 "${token}"；只接受一个反馈 ID 与 key=value 字段`);
		}
		const key = token.slice(0, equals);
		const value = token.slice(equals + 1);
		if (HOST_ONLY_FIELDS.has(key)) {
			return badArgs(sub, `参数 "${key}" 属于 host/真实 UI 事实，不能由命令参数提供（拒绝自证身份/授权/根路径）`);
		}
		if (!allowedFields(sub).has(key)) return badArgs(sub, `子命令 ${sub} 不接受参数 "${key}"`);
		if (fields.has(key)) return badArgs(sub, `重复参数 "${key}"`);
		fields.set(key, value);
	}
	if ((sub === "retry" || sub === "update" || sub === "reply") && id === null) {
		return badArgs(sub, "缺少反馈 ID");
	}
	if (id !== null && !isIssueId(id)) return badArgs(sub, "反馈 ID 无效（应为 fb- 加 32 位小写十六进制）");
	return { sub, id, fields, error: null };
}

// ── Trusted-window gate and real UI confirmation ───────────────────────────

function gateReason(deps: IssueCommandDeps, sub: IssueSubcommand): string | null {
	const { host, ui } = deps;
	if (host.role !== "pm") return "仅项目/开发仓 PM 窗口可使用 /mw issue（host 观察角色不是 pm）";
	if (host.trustedWindow !== true) return "非可信窗口：窗口信任事实未由 host/真实 UI 证明";
	if (ui.hasUI !== true) return "无交互 UI，无法完成真实确认与完整预览展示";
	if (WRITE_SUBCOMMANDS.has(sub) && host.writeAuthorized !== true) return "窗口未被 host 授权写入";
	return null;
}

function projectActor(host: IssueCommandHost): IssueStoreActor {
	return {
		role: host.role,
		scope: "project",
		projectRoot: host.projectRoot,
		projectLabel: host.projectLabel,
		by: host.by,
		trustedWindow: host.trustedWindow === true,
		writeAuthorized: host.writeAuthorized === true,
	};
}

function devActor(host: IssueCommandHost, devRoot: string): IssueStoreActor {
	return {
		role: host.role,
		scope: "dev",
		projectRoot: devRoot,
		projectLabel: host.projectLabel,
		by: host.by,
		trustedWindow: host.trustedWindow === true,
		writeAuthorized: host.writeAuthorized === true,
	};
}

async function showFull(ui: IssueCommandUI, title: string, text: string): Promise<void> {
	if (ui.present !== undefined) await ui.present(title, text);
	else ui.notify(text, "info");
}

interface ConfirmationOutcome {
	readonly confirmed: boolean;
	readonly reason: string;
}

/** Show the COMPLETE text, then require the real dialog's boolean `true`.
 * The confirm message is the same full string — no summary, no truncation. */
async function confirmExact(ui: IssueCommandUI, title: string, preview: string): Promise<ConfirmationOutcome> {
	let answer: unknown;
	try {
		// Both the presentation and the dialog must succeed. A thrown/missing
		// preview surface is a refusal, never a silent shortcut to the write.
		await showFull(ui, title, preview);
		answer = await ui.confirm(title, preview);
	} catch (error) {
		const detail = error instanceof Error ? error.message : String(error);
		return { confirmed: false, reason: `确认/预览界面异常: ${detail}；未执行任何写入` };
	}
	if (answer !== true) {
		return { confirmed: false, reason: "未获得明确确认（取消/超时/未返回 true）；未执行任何写入" };
	}
	return { confirmed: true, reason: "用户已确认完整脱敏预览" };
}

function cleanText(text: string, knownSecrets: readonly string[], mode: IssueTextMode = "canonical"): string {
	// redactSecrets keeps its credential contract (signature/count/semantics).
	// The explicit mode selects one raw ingress encoding or the canonical fixed
	// point; no token matching, cache or clock guesses the source. The SAME text
	// feeds the store-template preview, confirm dialog, payload and result.
	return normalizeIssueText(redactSecrets(text, knownSecrets).text, mode, REDACTION_MARK).text;
}

/** Report fields remain RAW in memory; prepareIssue owns their single encoding. */
function redactRawText(text: string, knownSecrets: readonly string[]): string {
	return redactSecrets(text, knownSecrets).text;
}

function rootFailureLine(failure: IssueDevRootFailure | null): string {
	return failure === null ? "" : `\n- 权威根定位失败: ${formatIssueDevRootFailure(failure)}（不猜测根路径）`;
}

function storeFailure(sub: IssueSubcommand, method: string, error: unknown): IssueCommandResult {
	const code = error instanceof IssueStoreError ? error.code : "E-ISSUE-COMMAND-STORE";
	const detail = error instanceof Error ? error.message : String(error);
	const message = `存储层异常，未写入: ${detail}`;
	return makeResult({
		sub,
		code,
		message,
		text: `# /mw issue ${sub} — 存储异常\n- ${code}: ${detail}\n- 未执行任何静默修复。`,
		writesAttempted: [method],
	});
}

// ── Guided report form ──────────────────────────────────────────────────────

interface FieldSpec {
	readonly key: string;
	readonly prompt: string;
	readonly multiline: boolean;
}

const REPORT_PROMPTS: readonly FieldSpec[] = [
	{ key: "title", prompt: "一句话现象（短标题；留空=未知，不推断）", multiline: false },
	{ key: "component", prompt: "MW 组件/入口（不确定留空=待分诊）", multiline: false },
	{
		key: "occurredAt",
		prompt: "故障发生时间（带时区 ISO，如 2026-11-12T14:02:11+08:00；留空=未知）",
		multiline: false,
	},
	{ key: "trigger", prompt: "触发操作（做了什么、哪条 /mw 操作）", multiline: false },
	{ key: "precondition", prompt: "前置条件（故障时状态；留空=未知）", multiline: false },
	{ key: "expected", prompt: "预期结果", multiline: false },
	{ key: "actual", prompt: "实际结果", multiline: false },
	{ key: "impact", prompt: "影响（卡住/丢结果/误提示等）", multiline: false },
	{ key: "steps", prompt: "最短复现步骤（不能复现就写“复现未知/仅发生一次”；原文不截断）", multiline: true },
	{ key: "frequency", prompt: "复现频率（每次/偶发/未知；留空=未知）", multiline: false },
	{ key: "error", prompt: "关键错误片段（用户选择，原文不截断；留空=未知）", multiline: true },
	{ key: "mwVersion", prompt: "故障时 MW 版本（用户陈述；留空=未知）", multiline: false },
	{ key: "piVersion", prompt: "故障时 pi 版本（用户陈述；留空=未知）", multiline: false },
	{ key: "platform", prompt: "故障时平台（用户陈述；留空=未知）", multiline: false },
	{ key: "windowType", prompt: "故障时窗口类型（用户陈述；留空=未知）", multiline: false },
	{
		key: "diagnostic",
		prompt: "可选诊断片段（仅用户主动提供、确认前脱敏；留空=不附，不自动读取日志/源码）",
		multiline: true,
	},
];

interface CollectedFields {
	readonly values: ReadonlyMap<string, string>;
	readonly error: string | null;
}

async function collectReportFields(args: ReadonlyMap<string, string>, ui: IssueCommandUI): Promise<CollectedFields> {
	const values = new Map<string, string>(args);
	for (const spec of REPORT_PROMPTS) {
		if (values.has(spec.key)) continue;
		const answer = spec.multiline ? await ui.editor(spec.prompt) : await ui.input(spec.prompt);
		if (answer === undefined) {
			return { values, error: `采集已取消（${spec.key}），未提交任何内容` };
		}
		values.set(spec.key, answer);
	}
	return { values, error: null };
}

interface BuiltReport {
	readonly draft: IssueDraft;
	readonly environmentObservedAt: string | null;
	readonly notes: readonly string[];
}

function asUser(raw: string | undefined, at: string, knownSecrets: readonly string[]): Observation {
	const value = (raw ?? "").trim();
	return value === "" ? unknownObservation() : userObservation(redactRawText(value, knownSecrets), at);
}

function asObserved(raw: string | undefined, at: string | null, knownSecrets: readonly string[]): Observation {
	const value = (raw ?? "").trim();
	if (value === "" || at === null || !isInstant(at)) return unknownObservation();
	return observedObservation(redactRawText(value, knownSecrets), at);
}

function buildReportDraft(
	values: ReadonlyMap<string, string>,
	host: IssueCommandHost,
	id: string,
	windowAt: string,
): BuiltReport {
	const knownSecrets = host.knownSecrets;
	const notes: string[] = [];
	const observedAtRaw = host.observedEnvironment?.observedAt ?? null;
	const environmentObservedAt = observedAtRaw !== null && isInstant(observedAtRaw) ? observedAtRaw : null;
	if (host.observedEnvironment !== null && environmentObservedAt === null) {
		notes.push("窗口实测环境缺合法采集时间，全部按未知处理（当前读数不冒充故障时快照）");
	}
	const observedValues = host.observedEnvironment?.values ?? {};
	const envAtFailure = {
		mwVersion: asUser(values.get("mwVersion"), windowAt, knownSecrets),
		piVersion: asUser(values.get("piVersion"), windowAt, knownSecrets),
		platform: asUser(values.get("platform"), windowAt, knownSecrets),
		windowType: asUser(values.get("windowType"), windowAt, knownSecrets),
	};
	const observedEnvironment: ObservedEnvironmentFacts = {
		mwVersion: asObserved(observedValues.mwVersion, environmentObservedAt, knownSecrets),
		piVersion: asObserved(observedValues.piVersion, environmentObservedAt, knownSecrets),
		platform: asObserved(observedValues.platform, environmentObservedAt, knownSecrets),
		windowType: asObserved(observedValues.windowType, environmentObservedAt, knownSecrets),
		bundleStatus: asObserved(observedValues.bundleStatus, environmentObservedAt, knownSecrets),
		serveStatus: asObserved(observedValues.serveStatus, environmentObservedAt, knownSecrets),
	};
	const occurredRaw = (values.get("occurredAt") ?? "").trim();
	let occurredAt: Observation = unknownObservation();
	if (occurredRaw !== "") {
		if (isInstant(occurredRaw)) occurredAt = userObservation(redactRawText(occurredRaw, knownSecrets), windowAt);
		else notes.push("故障发生时间缺时区或非法，按未知处理（不推断）");
	}
	const frequencyRaw = (values.get("frequency") ?? "").trim();
	let frequency: ReproductionFrequency = "未知";
	if (frequencyRaw !== "") {
		if (REPRODUCTION_FREQUENCIES.includes(frequencyRaw as ReproductionFrequency)) {
			frequency = frequencyRaw as ReproductionFrequency;
		} else notes.push("复现频率取值无效，按未知处理");
	}
	const candidates: DiagnosticCandidate[] = [];
	const selected: string[] = [];
	const diagnostic = (values.get("diagnostic") ?? "").trim();
	if (diagnostic !== "") {
		const kindRaw = (values.get("diagnosticKind") ?? "").trim();
		const kind: DiagnosticCandidate["kind"] = kindRaw === "log" || kindRaw === "attachment-ref" ? kindRaw : "error";
		candidates.push({ id: "diag-1", kind, text: redactRawText(diagnostic, knownSecrets) });
		selected.push("diag-1");
	}
	const unselected = (values.get("candidate") ?? "").trim();
	if (unselected !== "") {
		// Explicitly unselected candidate: in-memory only, never in the preview
		// or the store payload (AC-002 "未经确认内容不进入权威记录").
		candidates.push({ id: "unselected-1", kind: "log", text: redactRawText(unselected, knownSecrets) });
		notes.push("1 个未选择的诊断片段仅留在内存，未进入载荷");
	}
	const draft: IssueDraft = {
		id,
		title: redactRawText((values.get("title") ?? "").trim(), knownSecrets) || UNKNOWN,
		projectLabel: host.projectLabel,
		component: asUser(values.get("component"), windowAt, knownSecrets),
		occurredAt,
		trigger: asUser(values.get("trigger"), windowAt, knownSecrets),
		precondition: asUser(values.get("precondition"), windowAt, knownSecrets),
		expected: asUser(values.get("expected"), windowAt, knownSecrets),
		actual: asUser(values.get("actual"), windowAt, knownSecrets),
		impact: asUser(values.get("impact"), windowAt, knownSecrets),
		reproductionSteps: asUser(values.get("steps"), windowAt, knownSecrets),
		reproductionFrequency: frequency,
		errorExcerpt: asUser(values.get("error"), windowAt, knownSecrets),
		environmentAtFailure: envAtFailure,
		observedEnvironment,
		diagnosticCandidates: candidates,
		selectedFragmentIds: selected,
	};
	return { draft, environmentObservedAt, notes };
}

function renderReportText(result: IssueSubmitResult, preview: string, notes: readonly string[]): string {
	// Idempotent display defense for any out-of-band value; canonical values are
	// already neutralized so this is a no-op on the confirmed preview/payload.
	return escapeUntrustedText(
		[
			"# MW 问题反馈 — 提交结果",
			`- 反馈 ID: ${escapeIssueIdentity(result.id)}`,
			`- 结果: ${result.display}（${result.code}）`,
			`- 说明: ${result.message}`,
			`- 原因: ${result.reason}`,
			`- 权威记录可达: ${result.authorityReachable ? "是" : "否"}`,
			`- 重试次数: ${result.attempts}`,
			"- 时间来源: 故障发生时间由提交者陈述；提交时间与环境采集时间由窗口记录，互不替代。",
			...notes.map((note) => `- 采集/脱敏备注: ${note}`),
			"\n## 确认时展示的完整脱敏问题卡（与写入内容一致）",
			preview,
			"\n## 边界",
			`- ${ISSUE_STORE_ENTRY_ONLY_NOTICE}`,
			rootFailureLine(result.rootFailure),
		].join("\n"),
	);
}

async function runReport(deps: IssueCommandDeps, args: ReadonlyMap<string, string>): Promise<IssueCommandResult> {
	const { host, ui, store } = deps;
	const windowAt = host.now();
	if (!isInstant(windowAt)) return refused("report", "invalid-window-time", "窗口时钟未提供合法带时区时间，拒绝提交");
	const collected = await collectReportFields(args, ui);
	if (collected.error !== null) return refused("report", "cancelled", collected.error);
	const built = buildReportDraft(collected.values, host, (deps.newId ?? newIssueId)(), windowAt);
	const preparation = prepareIssue(built.draft, {
		submittedAt: windowAt,
		environmentObservedAt: built.environmentObservedAt,
		knownSecrets: host.knownSecrets,
		textMode: "raw",
	});
	if (issueTextSha256(preparation.preview) !== preparation.previewSha256) {
		return refused("report", "preview-mismatch", "完整预览摘要不一致，拒绝提交");
	}
	const outcome = await confirmExact(ui, "确认提交以下完整脱敏问题卡？", preparation.preview);
	if (!outcome.confirmed) {
		return makeResult({
			sub: "report",
			code: "unconfirmed",
			message: outcome.reason,
			text: `# /mw issue report — 未提交\n- ${outcome.reason}\n- 共享端新增记录数为 0。`,
			preview: preparation.preview,
			previewSha256: preparation.previewSha256,
			confirmed: false,
			refused: true,
			notes: preparation.notes,
		});
	}
	const confirmedAt = host.now();
	if (!isInstant(confirmedAt)) return refused("report", "invalid-window-time", "确认时间缺时区，拒绝提交");
	const confirmation: Confirmation = {
		confirmed: true,
		confirmedAt,
		previewSha256: preparation.previewSha256,
	};
	const request: IssueSubmitRequest = {
		actor: projectActor(host),
		preparation,
		confirmation,
		knownSecrets: host.knownSecrets,
	};
	let result: IssueSubmitResult;
	try {
		result = await store.submit(request);
	} catch (error) {
		return storeFailure("report", "submit", error);
	}
	const notes = [
		...built.notes,
		...preparation.notes,
		`脱敏仅使用调用方明确提供的 ${host.knownSecrets.length} 项瞬时 knownSecrets；未扫描 env/auth、未读取日志/源码`,
	];
	return makeResult({
		ok: result.ok,
		sub: "report",
		code: result.code,
		message: result.message,
		text: renderReportText(result, preparation.preview, notes),
		id: result.id,
		display: result.display,
		preview: preparation.preview,
		previewSha256: preparation.previewSha256,
		confirmed: true,
		writesAttempted: ["submit"],
		notes,
		rootFailure: result.rootFailure,
	});
}

// ── retry / status / list ───────────────────────────────────────────────────

async function runRetry(deps: IssueCommandDeps, id: string): Promise<IssueCommandResult> {
	let result: IssueSubmitResult;
	try {
		result = await deps.store.retry({ actor: projectActor(deps.host), id });
	} catch (error) {
		return storeFailure("retry", "retry", error);
	}
	const text = [
		"# MW 问题反馈 — 同一 ID 重试",
		`- 反馈 ID: ${escapeIssueIdentity(result.id)}`,
		`- 结果: ${result.display}（${result.code}）`,
		`- 说明: ${result.message}`,
		`- 原因: ${result.reason}`,
		`- 重试次数: ${result.attempts}`,
		"- 不重建新 issue：仅从已确认的脱敏待发副本或按 ID 查证权威记录。",
		rootFailureLine(result.rootFailure),
	].join("\n");
	return makeResult({
		ok: result.ok,
		sub: "retry",
		code: result.code,
		message: result.message,
		text,
		id: result.id,
		display: result.display,
		writesAttempted: ["retry"],
		rootFailure: result.rootFailure,
	});
}

/** User-facing status projection. `status.pendingQuestion` is rendered from
 * the result field, NOT from `status.text`'s last-update "待补充问题" line. */
export function renderIssueStatusText(status: IssueStatusResult): string {
	const development = status.development;
	const effective = status.localEffective;
	const phrase = effective === null || effective.phrase === VERIFIED_PHRASE ? NOT_VERIFIED_PHRASE : effective.phrase;
	// First-phase fail-closed: a future store projection that claims "已验证用上
	// 修复" has no artifact->install->running-process identity chain, so the
	// window never lets that claim through — including inside `status.text`.
	const body = status.text.includes(VERIFIED_PHRASE)
		? status.text.replaceAll(VERIFIED_PHRASE, NOT_VERIFIED_PHRASE)
		: status.text;
	return escapeUntrustedText(
		[
			`# 问题卡 ${escapeIssueIdentity(status.id)} — 反馈回查`,
			`- 本地回执: ${status.display}（${status.code}）`,
			`- 权威记录可达: ${status.authorityReachable ? "是" : "否"}`,
			`- 查询说明: ${status.message}`,
			body,
			"\n## 最近未回复追问（显式取自 status.pendingQuestion，不以最后一次进展字段为准）",
			`- ${status.pendingQuestion ?? "无"}`,
			"\n## 开发侧进展（开发侧解释，与报障事实分栏）",
			`- 当前状态: ${development?.status ?? UNKNOWN}`,
			`- 状态原因/分诊结论: ${development?.statusNote ?? UNKNOWN}`,
			`- 下一步/受阻原因: ${development?.nextAction ?? UNKNOWN}`,
			`- 修复提交: ${development?.fixCommit ?? UNKNOWN}`,
			`- 发布版本: ${development?.releaseVersion ?? UNKNOWN}`,
			`- 最后更新时间: ${development?.updatedAt ?? UNKNOWN}`,
			`- 更新者: ${development?.by ?? UNKNOWN}`,
			"\n## 本项目使用情况（开发侧状态 ≠ 本项目已用上修复）",
			`- ${phrase}（state=${effective?.state ?? "unknown"}；${effective?.reason ?? "权威状态无法更新，无本地生效证据"}）`,
			"- 首期缺少修复产物→安装→运行身份链的可验证一致性证据；无法证明时一律标未验证。",
			"\n## 后续消息",
			"- 开发进展与项目回复均为同一 ID 的追加事件；故障最初现场与信息原文不被后续消息覆盖。",
			rootFailureLine(status.rootFailure),
		].join("\n"),
	);
}

export function renderIssueListText(list: IssueListResult): string {
	const lines = [
		"# 本项目登记的反馈 ID（无 ID 时只列本项目）",
		`- 权威记录可达: ${list.authorityReachable ? "是" : "否"}`,
		`- ${list.message}`,
	];
	if (!list.authorityReachable) lines.push("- 状态无法更新，不展示过期开发进展；开发状态一律为未知。");
	if (list.rows.length === 0) lines.push(`- ${UNKNOWN}（本项目未登记反馈 ID）`);
	for (const row of list.rows) {
		lines.push(
			`- ${escapeIssueIdentity(row.id)} | ${row.title} | 开发状态: ${row.status} | 最后更新: ${row.updatedAt ?? UNKNOWN} | 待补充: ${
				row.needsReply ? "是" : "否"
			} | 本地状态: ${row.localState}`,
		);
	}
	lines.push(rootFailureLine(list.rootFailure));
	return escapeUntrustedText(lines.join("\n"));
}

// ── dev-authority inbox (T-09B): explicit /mw issue inbox [id], read-only ──

const ISSUE_INCOMING_BOUNDARY = [
	"- 开发侧状态仅来自权威事件回放，不等于任意项目本地安装/已用上修复；项目本地生效仍以各自证据为准。",
	"- 本入口只读 events 目录：未写权威、时间线、项目本地 index/ACK/state，未创建目录或锁；损坏/离线显式报错，不静默修复。",
	"- 普通项目仍只能用 /mw issue status/list 查看本项目登记的 ID；foreign-ID status 未被放宽。",
].join("\n");

/** No-ID inbox: enumerate the authority's incoming cards. `needsReply` comes
 * from the store's stable dev_update.sha256 identity projection; rows carry NO
 * localState/submitted/ACK/localEffective columns. */
export function renderIssueIncomingListText(list: IssueIncomingListResult): string {
	const lines = [
		"# MW 开发仓权威收件箱（仅经核验 dev 窗口；无 ID 枚举）",
		`- 结果: ${list.ok ? "可枚举" : "拒绝/未知"}（${list.code}）`,
		`- ${list.message}`,
		`- 原因: ${list.reason}`,
		`- 收件数: ${list.rows.length}`,
		"- 来源: 显式验证开发根下的 authority/events（只读；无项目本地 index/ACK/state）",
	];
	if (list.rows.length === 0) lines.push(`- ${UNKNOWN}（未列出任何权威收件卡）`);
	for (const row of list.rows) {
		lines.push(
			`- ${escapeIssueIdentity(row.id)} | 来源项目: ${escapeIssueIdentity(row.projectLabel)} | 标题: ${row.title} | 开发状态: ${row.status} | 最后更新: ${
				row.updatedAt ?? UNKNOWN
			} | 待补充: ${row.needsReply ? "是" : "否"}`,
		);
	}
	lines.push("\n## 边界", ISSUE_INCOMING_BOUNDARY);
	if (list.rootFailure !== null) {
		lines.push(`- 权威根定位失败: ${formatIssueDevRootFailure(list.rootFailure)}（不猜测根路径）`);
	}
	return escapeUntrustedText(lines.join("\n"));
}

/** Every historical question keyed by its REAL dev_update event hash. A reply
 * clears only the hash it references: an older question stays visible as
 * history, never re-floats as the pending question. Time/null references are
 * supplements and match no event hash. */
function renderIncomingQuestionHistory(events: IssueIncomingReadResult["events"]): string[] {
	const answered = new Set<string>();
	for (const event of events) {
		if (event.kind === "reporter_reply" && event.reply.inReplyTo !== null) answered.add(event.reply.inReplyTo);
	}
	const lines: string[] = [];
	for (const event of events) {
		if (event.kind !== "dev_update") continue;
		const question = event.update.questionToReporter;
		if (question === null || question.trim() === "") continue;
		lines.push(
			`- #${event.seq} [${event.sha256.slice(0, 8)}] ${answered.has(event.sha256) ? "已回复" : "未回复"}: ${question}`,
		);
	}
	if (lines.length === 0) lines.push("- 无（尚无带追问的开发进展事件）");
	return lines;
}

/** Display every verified authority event in its REAL seq/append order. This
 * timeline is historical only: it never sorts by clock, drops duplicate text,
 * skips a zero-question update, repeats the created card, or turns an old
 * status/version into the current state / a local-effectiveness claim. */
function renderIncomingEventTimeline(events: IssueIncomingReadResult["events"]): string[] {
	const nullable = (value: string | null): string => value ?? UNKNOWN;
	const lines: string[] = [
		"\n## 权威事件时间线（仅历史，按 seq/追加顺序；不是当前状态或本地生效）",
		"- 原始 created 现场、三时刻/source 仍由下方既有完整卡展示；此栏不重复序列化整卡或任何原始 secret。",
	];
	for (const event of events) {
		lines.push(
			`- #${event.seq} ${event.kind} | seq=${event.seq} | id=${event.id} | at=${event.at} | source=${event.source} | by=${event.by}`,
			`- sha256=${event.sha256} | prev_sha256=${event.prev_sha256} | project_label=${escapeIssueIdentity(event.project_label)} | submission_digest=${event.submission_digest}`,
		);
		if (event.kind === "created") {
			lines.push(
				`- confirmed_at=${event.confirmed_at} | confirmed_by=${event.confirmed_by} | card_sha256=${event.card_sha256} | preview_sha256=${event.preview_sha256}`,
			);
			continue;
		}
		if (event.kind === "dev_update") {
			lines.push(
				`- update.at=${event.update.at} | update.by=${event.update.by} | status=${event.update.status} | statusNote=${event.update.statusNote} | nextAction=${nullable(event.update.nextAction)} | fixCommit=${nullable(event.update.fixCommit)} | releaseVersion=${nullable(event.update.releaseVersion)} | questionToReporter=${nullable(event.update.questionToReporter)}`,
			);
			continue;
		}
		const target = event.reply.inReplyTo;
		const linked = target === null ? undefined : events.find((candidate) => candidate.sha256 === target);
		lines.push(
			`- reply.at=${event.reply.at} | reply.source=${event.reply.source} | reply.text=${event.reply.text} | reply.inReplyTo=${nullable(target)}`,
			linked === undefined
				? "- 关联: 无权威事件（补充信息）"
				: `- 关联 #${linked.seq} ${linked.kind} sha256=${linked.sha256}`,
		);
	}
	return lines;
}

/** With-ID inbox: the complete confirmed redacted card (three times, sources,
 * diagnostics, dev progress and same-ID replies) plus the EXPLICIT pending
 * question. The last dev update's `questionToReporter` is never used as the
 * pending question, and no local-effectiveness verdict is fabricated. */
export function renderIssueIncomingCardText(read: IssueIncomingReadResult): string {
	if (!read.ok) return escapeUntrustedText(read.text);
	const development = read.development;
	const lines = [
		`# MW 开发仓权威收件卡 ${escapeIssueIdentity(read.id)} — 只读回放`,
		`- 结果: 已打开（${read.code}）`,
		`- 说明: ${read.message}`,
		`- 原因: ${read.reason}`,
		`- 来源项目（非敏感标识，不是安装证据）: ${read.projectLabel === null ? UNKNOWN : escapeIssueIdentity(read.projectLabel)}`,
		`- 权威事件数: ${read.events.length}`,
		"\n## 最近未回复追问（按 dev_update.sha256 事件身份判定；不以最后一条 update.questionToReporter 冒充）",
		`- ${read.pendingQuestion ?? "无"}`,
		"\n## 追问历史（按 dev_update.sha256 事件身份；旧问只留历史，不回浮）",
		...renderIncomingQuestionHistory(read.events),
		...renderIncomingEventTimeline(read.events),
		"\n## 开发侧进展（权威记录，与报障事实分栏）",
		`- 当前状态: ${development?.status ?? UNKNOWN}`,
		`- 状态原因/分诊结论: ${development?.statusNote ?? UNKNOWN}`,
		`- 下一步/受阻原因: ${development?.nextAction ?? UNKNOWN}`,
		`- 修复提交: ${development?.fixCommit ?? UNKNOWN}`,
		`- 发布版本: ${development?.releaseVersion ?? UNKNOWN}`,
		`- 最后更新时间: ${development?.updatedAt ?? UNKNOWN}`,
		`- 更新者: ${development?.by ?? UNKNOWN}`,
		"\n## 用户已确认脱敏卡、三时刻/source、进展与同 ID 回复（完整、不截断）",
		read.text,
		"\n## 边界",
		ISSUE_INCOMING_BOUNDARY,
	];
	if (read.rootFailure !== null) {
		lines.push(`- 权威根定位失败: ${formatIssueDevRootFailure(read.rootFailure)}（不猜测根路径）`);
	}
	return escapeUntrustedText(lines.join("\n"));
}

async function runInbox(deps: IssueCommandDeps, id: string | null): Promise<IssueCommandResult> {
	// The host supplies devRoot ONLY after the real window proves current
	// canonical root == explicitly validated dev root (T-05). The store re-checks
	// it independently; a null root is a refusal, never a guessed path.
	const devRoot = deps.host.devRoot;
	if (devRoot === null) {
		return refused(
			"inbox",
			"invalid-host",
			"开发仓收件箱必须由 host 提供经显式验证的 devRoot（当前 canonical root == 验证开发根、真实 PM/TUI 窗口）；拒绝读取，不回退错根",
		);
	}
	const actor = devActor(deps.host, devRoot);
	if (id === null) {
		let list: IssueIncomingListResult;
		try {
			list = await deps.store.listIncoming({ actor });
		} catch (error) {
			return storeFailure("inbox", "listIncoming", error);
		}
		return makeResult({
			ok: list.ok,
			sub: "inbox",
			code: list.code,
			message: list.message,
			text: renderIssueIncomingListText(list),
			rootFailure: list.rootFailure,
		});
	}
	let read: IssueIncomingReadResult;
	try {
		read = await deps.store.readIncoming({ actor, id });
	} catch (error) {
		return storeFailure("inbox", "readIncoming", error);
	}
	return makeResult({
		ok: read.ok,
		sub: "inbox",
		code: read.code,
		message: read.message,
		text: renderIssueIncomingCardText(read),
		id: read.id,
		pendingQuestion: read.pendingQuestion,
		development: read.development,
		rootFailure: read.rootFailure,
	});
}

async function runStatus(deps: IssueCommandDeps, id: string | null, ui: IssueCommandUI): Promise<IssueCommandResult> {
	const actor = projectActor(deps.host);
	if (id === null) {
		let list: IssueListResult;
		try {
			list = await deps.store.list({ actor });
		} catch (error) {
			return storeFailure("status", "list", error);
		}
		const text = renderIssueListText(list);
		await showFull(ui, "MW 反馈列表", text);
		return makeResult({
			ok: list.ok,
			sub: "status",
			code: list.code,
			message: list.message,
			text,
			rows: list.rows,
			rootFailure: list.rootFailure,
		});
	}
	const request: IssueStatusRequest = {
		actor,
		id,
		...(deps.host.localEvidence === null ? {} : { localEvidence: deps.host.localEvidence }),
	};
	let status: IssueStatusResult;
	try {
		status = await deps.store.status(request);
	} catch (error) {
		return storeFailure("status", "status", error);
	}
	const text = renderIssueStatusText(status);
	await showFull(ui, `MW 问题卡 ${id}`, text);
	return makeResult({
		ok: status.ok,
		sub: "status",
		code: status.code,
		message: status.message,
		text,
		id: status.id,
		display: status.display,
		pendingQuestion: status.pendingQuestion,
		development: status.development,
		localEffective: status.localEffective,
		rootFailure: status.rootFailure,
	});
}

// ── update / reply: same ID, one full redacted preview + one confirmation ───

const UPDATE_OPTIONAL_PROMPTS: readonly FieldSpec[] = [
	{ key: "statusNote", prompt: "状态原因/分诊结论（已知才写；留空=未知）", multiline: false },
	{ key: "nextAction", prompt: "下一步/受阻原因（留空=未知）", multiline: false },
	{ key: "fixCommit", prompt: "修复提交（已知才写；留空=未知）", multiline: false },
	{ key: "releaseVersion", prompt: "发布版本（已知才写；留空=未知）", multiline: false },
	{ key: "question", prompt: "向反馈方的具体补充追问（不需要就留空；不重复追问也保留上一次）", multiline: false },
];

async function collectOptionalFields(
	args: ReadonlyMap<string, string>,
	specs: readonly FieldSpec[],
	ui: IssueCommandUI,
): Promise<CollectedFields> {
	const values = new Map<string, string>(args);
	for (const spec of specs) {
		if (values.has(spec.key)) continue;
		const answer = spec.multiline ? await ui.editor(spec.prompt) : await ui.input(spec.prompt);
		if (answer === undefined) return { values, error: `采集已取消（${spec.key}），未写入` };
		values.set(spec.key, answer);
	}
	return { values, error: null };
}

function nullableClean(raw: string | undefined, knownSecrets: readonly string[]): string | null {
	const value = (raw ?? "").trim();
	return value === "" ? null : cleanText(value, knownSecrets, "raw");
}

function renderMutationText(title: string, result: IssueMutationResult, preview: string): string {
	return escapeUntrustedText(
		[
			`# ${title} — 同一反馈 ID ${result.id}`,
			`- 结果: ${result.ok ? "已写入" : "未写入"}（${result.code}）`,
			`- 说明: ${result.message}`,
			`- 原因: ${result.reason}`,
			`- 事件序号: ${result.seq}`,
			"- 不新建反馈 ID；原项目回复与开发进展均为追加消息，不覆盖最初现场。",
			"\n## 确认时展示的完整脱敏预览（写入内容一致）",
			preview,
			rootFailureLine(result.rootFailure),
		].join("\n"),
	);
}

async function runUpdate(
	deps: IssueCommandDeps,
	id: string,
	args: ReadonlyMap<string, string>,
): Promise<IssueCommandResult> {
	const { host, ui, store } = deps;
	if (host.devRoot === null) {
		return refused("update", "invalid-host", "开发仓 PM 窗口必须由 host 提供 devRoot 才能登记进展；拒绝写入");
	}
	const collected = await collectOptionalFields(args, UPDATE_OPTIONAL_PROMPTS, ui);
	if (collected.error !== null) return refused("update", "cancelled", collected.error);
	let statusValue = collected.values.get("status");
	if (statusValue === undefined || statusValue.trim() === "") {
		const choice = await ui.select("选择开发状态（取消则不写入）", DEV_STATUSES);
		if (choice === undefined) return refused("update", "cancelled", "未选择开发状态，未写入");
		statusValue = choice;
	}
	if (!DEV_STATUSES.includes(statusValue.trim() as DevStatus)) {
		return refused("update", "invalid-status", `开发状态必须是 ${DEV_STATUSES.join("/")} 之一`);
	}
	const at = host.now();
	if (!isInstant(at)) return refused("update", "invalid-window-time", "窗口时钟未提供合法带时区时间，拒绝写入");
	const knownSecrets = host.knownSecrets;
	const update: IssueProgressFields = {
		status: statusValue.trim() as DevStatus,
		statusNote: nullableClean(collected.values.get("statusNote"), knownSecrets) ?? UNKNOWN,
		nextAction: nullableClean(collected.values.get("nextAction"), knownSecrets),
		fixCommit: nullableClean(collected.values.get("fixCommit"), knownSecrets),
		releaseVersion: nullableClean(collected.values.get("releaseVersion"), knownSecrets),
		questionToReporter: nullableClean(collected.values.get("question"), knownSecrets),
	};
	const preview = renderDevUpdatePreview(update, { id, at, source: "dev-pm", by: host.by });
	const previewSha256 = issueTextSha256(preview);
	const outcome = await confirmExact(ui, "确认写入以下完整脱敏开发进展？", preview);
	if (!outcome.confirmed) {
		return makeResult({
			sub: "update",
			code: "unconfirmed",
			message: outcome.reason,
			text: `# /mw issue update — 未写入\n- ${outcome.reason}`,
			preview,
			previewSha256,
			confirmed: false,
			refused: true,
		});
	}
	const request: IssueProgressRequest = {
		actor: devActor(host, host.devRoot),
		id,
		update,
		preview,
		confirmation: { confirmed: true, confirmedAt: at, previewSha256 },
		knownSecrets,
	};
	let result: IssueMutationResult;
	try {
		result = await store.appendProgress(request);
	} catch (error) {
		return storeFailure("update", "appendProgress", error);
	}
	return makeResult({
		ok: result.ok,
		sub: "update",
		code: result.code,
		message: result.message,
		text: renderMutationText("MW 反馈开发进展", result, preview),
		id: result.id,
		preview,
		previewSha256,
		confirmed: true,
		writesAttempted: ["appendProgress"],
		rootFailure: result.rootFailure,
	});
}

interface ReplyTarget {
	readonly inReplyTo: string | null;
	readonly failure: IssueCommandResult | null;
}

/** Resolve the event hash of the latest still-unanswered dev question from a
 * real store read. A reply is only bound to a KNOWN event of this same ID.
 * A failed/negative read is surfaced instead of silently dropping the link. */
async function resolveReplyTarget(store: IssueCommandStore, actor: IssueStoreActor, id: string): Promise<ReplyTarget> {
	let status: IssueStatusResult;
	try {
		status = await store.status({ actor, id });
	} catch (error) {
		return { inReplyTo: null, failure: storeFailure("reply", "status", error) };
	}
	if (!status.ok) {
		return {
			inReplyTo: null,
			failure: refused("reply", status.code, `无法核实追问事件：${status.message}`),
		};
	}
	if (status.pendingQuestion === null) return { inReplyTo: null, failure: null };
	for (let index = status.events.length - 1; index >= 0; index -= 1) {
		const event = status.events[index];
		if (event.kind === "dev_update") {
			const question = event.update.questionToReporter;
			if (question !== null && question.trim() !== "") return { inReplyTo: event.sha256, failure: null };
		}
	}
	return { inReplyTo: null, failure: null };
}

async function runReply(
	deps: IssueCommandDeps,
	id: string,
	fields: ReadonlyMap<string, string>,
): Promise<IssueCommandResult> {
	const { host, ui, store } = deps;
	let text = fields.get("text");
	if (text === undefined || text.trim() === "") {
		const answer = await ui.editor("回复正文（用户主动提供；确认前完整脱敏预览）");
		if (answer === undefined) return refused("reply", "cancelled", "回复采集已取消，未写入");
		text = answer;
	}
	const knownSecrets = host.knownSecrets;
	const clean = cleanText(text.trim(), knownSecrets, "raw");
	if (clean === "") return refused("reply", "missing-text", "回复正文为空，未写入");
	const at = host.now();
	if (!isInstant(at)) return refused("reply", "invalid-window-time", "窗口时钟未提供合法带时区时间，拒绝写入");
	const explicit = fields.get("inReplyTo");
	let inReplyTo: string | null;
	if (explicit !== undefined && explicit.trim() !== "") {
		// Event hashes / instants are canonical identifiers, never raw user text.
		inReplyTo = cleanText(explicit.trim(), knownSecrets);
	} else {
		const target = await resolveReplyTarget(store, projectActor(host), id);
		if (target.failure !== null) return target.failure;
		inReplyTo = target.inReplyTo;
	}
	const reply: IssueReplyFields = { text: clean, source: "user", inReplyTo };
	const preview = renderReporterReplyPreview(reply, { id, at, source: "project-pm", by: host.by });
	const previewSha256 = issueTextSha256(preview);
	const outcome = await confirmExact(ui, "确认写入以下完整脱敏项目回复？", preview);
	if (!outcome.confirmed) {
		return makeResult({
			sub: "reply",
			code: "unconfirmed",
			message: outcome.reason,
			text: `# /mw issue reply — 未写入\n- ${outcome.reason}`,
			preview,
			previewSha256,
			confirmed: false,
			refused: true,
		});
	}
	const request: IssueReplyRequest = {
		actor: projectActor(host),
		id,
		reply,
		preview,
		confirmation: { confirmed: true, confirmedAt: at, previewSha256 },
		knownSecrets,
	};
	let result: IssueMutationResult;
	try {
		result = await store.reply(request);
	} catch (error) {
		return storeFailure("reply", "reply", error);
	}
	return makeResult({
		ok: result.ok,
		sub: "reply",
		code: result.code,
		message: result.message,
		text: renderMutationText("MW 反馈项目回复", result, preview),
		id: result.id,
		preview,
		previewSha256,
		confirmed: true,
		writesAttempted: ["reply"],
		rootFailure: result.rootFailure,
	});
}

// ── bind: explicit pointer write only after a real UI confirmation ──────────

async function runBind(deps: IssueCommandDeps): Promise<IssueCommandResult> {
	const { host, ui } = deps;
	if (host.devRoot === null || host.pointerFile === null) {
		return refused("bind", "invalid-host", "绑定必须由 host 提供 devRoot 与显式 pointerFile；不隐式写本机配置");
	}
	const preview = [
		"# MW 开发仓本机绑定（确认后才写 pointer）",
		`- 调用窗口项目根: ${host.projectRoot}`,
		`- 候选开发仓根: ${host.devRoot}`,
		`- 显式 pointer 文件: ${host.pointerFile}`,
		"- 该绑定只是显式本机位置记录，不是 OS 权限授予、写者认证或仓库身份证明。",
		"- 其它项目仅只读消费该 pointer；权威记录仍在 MW 开发仓。",
	].join("\n");
	const previewSha256 = issueTextSha256(preview);
	const outcome = await confirmExact(ui, "确认绑定本机 MW 开发仓 pointer？", preview);
	if (!outcome.confirmed) {
		return makeResult({
			sub: "bind",
			code: "unconfirmed",
			message: outcome.reason,
			text: `# /mw issue bind — 未写入\n- ${outcome.reason}\n- 本机 pointer 新增记录数为 0。`,
			preview,
			previewSha256,
			confirmed: false,
			refused: true,
		});
	}
	const at = host.now();
	if (!isInstant(at)) return refused("bind", "invalid-window-time", "窗口时钟未提供合法带时区时间，拒绝写入");
	const bind = deps.bindRoot ?? bindIssueDevRoot;
	let result: BindIssueDevRootResult;
	try {
		result = bind({
			callerProjectRoot: host.projectRoot,
			candidateRoot: host.devRoot,
			userConfirmed: true,
			pointerFile: host.pointerFile,
			now: () => new Date(at),
		});
	} catch (error) {
		return storeFailure("bind", "bind", error);
	}
	if (!result.ok) {
		const message = formatIssueDevRootFailure(result);
		return makeResult({
			sub: "bind",
			code: result.code,
			message,
			text: `# /mw issue bind — 失败\n- ${message}\n- 未猜测或回退到其它根路径。`,
			preview,
			previewSha256,
			confirmed: true,
			writesAttempted: ["bind"],
			rootFailure: result,
		});
	}
	return makeResult({
		ok: true,
		sub: "bind",
		code: "bound",
		message: "已写入本机显式 pointer（非 OS 权限授予）",
		text: [
			"# MW 开发仓本机绑定 — 已写入",
			`- pointer 文件: ${result.pointerPath}`,
			`- 绑定根: ${result.canonicalRoot}`,
			"- 该绑定只是显式本机位置记录，不是 OS 权限授予或写者认证。",
			"\n## 确认时展示的完整预览",
			preview,
		].join("\n"),
		preview,
		previewSha256,
		confirmed: true,
		writesAttempted: ["bind"],
	});
}

// ── Single injectable entry point ───────────────────────────────────────────

/** `/mw issue <args>` handler face for T-05. All host facts, the UI adapter and
 * the store are injected; no cwd/env/credential discovery happens here. */
export async function handleIssueCommand(rawArgs: string, deps: IssueCommandDeps): Promise<IssueCommandResult> {
	const parsed = parseIssueCommandArgs(rawArgs);
	if (parsed.error !== null || parsed.sub === null) {
		const message = parsed.error ?? "未知 issue 子命令";
		const result = refused(
			parsed.sub ?? "unknown",
			parsed.sub === null ? "invalid-subcommand" : "invalid-args",
			message,
		);
		deps.ui.notify(result.message, "warning");
		return result;
	}
	const sub = parsed.sub;
	const gate = gateReason(deps, sub);
	if (gate !== null) {
		const result = refused(sub, "untrusted-window", `${gate}；拒绝执行`);
		deps.ui.notify(result.message, "warning");
		return result;
	}
	let result: IssueCommandResult;
	if (sub === "report") result = await runReport(deps, parsed.fields);
	else if (sub === "retry") result = await runRetry(deps, parsed.id ?? "");
	else if (sub === "status") result = await runStatus(deps, parsed.id, deps.ui);
	else if (sub === "inbox") result = await runInbox(deps, parsed.id);
	else if (sub === "update") result = await runUpdate(deps, parsed.id ?? "", parsed.fields);
	else if (sub === "reply") result = await runReply(deps, parsed.id ?? "", parsed.fields);
	else result = await runBind(deps);
	if (result.refused || !result.ok) deps.ui.notify(result.message, result.refused ? "warning" : "error");
	// `status` already showed its complete card inside runStatus; everything else
	// shows its complete (never truncated) result text exactly once here. A
	// presentation failure must not change an already-computed store outcome.
	if (result.sub !== "status" && result.text.length > 0) {
		try {
			await showFull(deps.ui, `MW issue ${sub}`, result.text);
		} catch {
			// T-05 still receives result.text; no write is retried here.
		}
	}
	return result;
}
