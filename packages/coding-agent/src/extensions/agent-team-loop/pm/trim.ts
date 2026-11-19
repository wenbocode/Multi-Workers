import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import * as path from "node:path";
import { Type } from "typebox";
import type { ExtensionAPI, ExtensionCommandContext } from "../../../core/extensions/types.ts";
import { type IndexStore, keyNameRefusal, normalizeKey } from "../shared/index-store.ts";
import { findMwPy, PYTHON_EXE } from "../shared/mw-runner.ts";
import { requestReplan } from "./replan.ts";

type TaskBasis = { task: string; issue: string; snapshot: string; status: string };
type Basis = { task: TaskBasis } | { sha: string };
type TrimRequest = {
	key: string;
	claim: string;
	task?: string;
	basis?: Basis;
	probe?: { id: string; basis: Basis };
	check?: string;
	changed: boolean;
	contextApplied: boolean;
};

const taskName = /^[A-Za-z0-9_][A-Za-z0-9_.-]{0,159}$/;
const summaryLimitBytes = 8 * 1024;

function compactPmState(project: string, key: string, claim: string, sha: string, summary: string) {
	const pointer = path.join(
		process.env.PI_CODING_AGENT_DIR || path.join(homedir(), ".pi", "agent"),
		"extensions",
		".mw-pm-state-path",
	);
	let script: string | undefined;
	try {
		script = readFileSync(pointer, "utf8").trim();
	} catch (error) {
		if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
		const mw = findMwPy();
		if (mw) script = path.join(path.dirname(mw), "pm_state.py");
	}
	if (!script || !path.isAbsolute(script)) throw new Error("找不到已安装的 PM 状态压缩器。");
	return spawnSync(
		PYTHON_EXE,
		[
			"-B",
			"-X",
			"utf8",
			script,
			"compact",
			"--project",
			project,
			"--key",
			key,
			"--summary",
			"-",
			"--apply",
			sha,
			"--window-claim-id",
			claim,
		],
		{ input: summary, encoding: "utf8", windowsHide: true, timeout: 30_000 },
	);
}

export function registerTrim(
	pi: ExtensionAPI,
	project: string,
	root: string,
	index: IndexStore,
	watchedKey: () => string | undefined,
	windowClaim: () => string,
): (args: string, ctx: ExtensionCommandContext) => void {
	let pending: TrimRequest | undefined;

	function owner(req: Pick<TrimRequest, "key" | "claim">) {
		const matches = index.readAll().filter((row) => normalizeKey(row.key) === normalizeKey(req.key));
		const row = matches[0];
		return matches.length === 1 && row?.key === req.key && row.status === "active" && row.claimId === req.claim
			? row.phase.toUpperCase()
			: undefined;
	}

	function prepareTask(req: TrimRequest, task: string) {
		const result = requestReplan(project, { operation: "inspect", key: req.key, claim: req.claim, task });
		const facts = result.facts;
		if (
			result.ok !== true ||
			typeof result.issue !== "string" ||
			typeof result.snapshot !== "string" ||
			typeof facts !== "object" ||
			facts === null ||
			!("task" in facts) ||
			typeof facts.task !== "string" ||
			!("status" in facts) ||
			typeof facts.status !== "string"
		) {
			throw new Error(String(result.reason ?? "无法读取任务状态"));
		}
		req.basis = { task: { task: facts.task, issue: result.issue, snapshot: result.snapshot, status: facts.status } };
		req.check = undefined;
		return result;
	}

	pi.on("tool_result", (event) => {
		const req = pending;
		if (!req?.basis) return;
		if (event.toolName === "bash" && req.probe?.id === event.toolCallId && req.probe.basis === req.basis) {
			req.check = event.isError ? undefined : event.toolCallId;
			req.probe = undefined;
		}
		if (
			event.toolName === "replan_tasks" &&
			event.input.operation === "apply" &&
			!event.isError &&
			typeof event.details === "object" &&
			event.details !== null &&
			"state" in event.details &&
			event.details.state === "applied"
		) {
			req.changed = true;
			req.basis = undefined;
			req.check = undefined;
		}
	});

	pi.on("tool_call", (event) => {
		const req = pending;
		if (!req) return;
		if (event.toolName === "bash" && req.basis) {
			req.probe = { id: event.toolCallId, basis: req.basis };
			req.check = undefined;
		}
		if (event.toolName !== "replan_tasks" || event.input.operation === "inspect") return;
		const basis = req.basis;
		if (
			!req.check ||
			!basis ||
			!("task" in basis) ||
			basis.task.status === "done" ||
			event.input.key !== req.key ||
			event.input.issue !== basis.task.issue ||
			event.input.snapshot !== basis.task.snapshot ||
			owner(req) !== "EXECUTE"
		) {
			return { block: true, reason: "先用 trim_progress 准备同一任务，再执行最小验证，随后复用 replan。" };
		}
	});

	pi.registerTool({
		name: "trim_progress",
		label: "Apply manual MW trim",
		description:
			"Use only during the user's /mw trim request. prepare_task refreshes the task snapshot; prepare_context snapshots its PM state after work trim. Run a focused bash check after preparing and then use steer or compact_context. Card changes go through replan_tasks.",
		parameters: Type.Object({
			operation: Type.Union([
				Type.Literal("prepare_task"),
				Type.Literal("steer"),
				Type.Literal("prepare_context"),
				Type.Literal("compact_context"),
			]),
			task: Type.Optional(Type.String()),
			remaining: Type.Optional(Type.String()),
			stop: Type.Optional(Type.String()),
			summary: Type.Optional(Type.String()),
		}),
		executionMode: "sequential",
		async execute(_id, params, signal, _update, ctx) {
			const req = pending;
			if (!req || signal?.aborted || req.contextApplied) throw new Error("没有可推进的手动 trim 请求");
			const phase = owner(req);
			if (phase !== "EXECUTE" && phase !== "VERIFY") throw new Error("当前窗口已失去执行阶段的 key 认领");
			const state = path.join(root, req.key, "pm-state.md");
			let result: Record<string, unknown>;
			if (params.operation === "prepare_task") {
				const task = params.task ?? req.task;
				if (phase !== "EXECUTE" || !task || !taskName.test(task) || (req.task && task !== req.task)) {
					throw new Error("请选择本次 trim 范围内的任务");
				}
				result = prepareTask(req, task);
			} else if (params.operation === "prepare_context") {
				if (req.task) throw new Error("单任务 trim 不会改动 key 的接续上下文");
				req.basis = { sha: createHash("sha256").update(readFileSync(state)).digest("hex") };
				req.check = undefined;
				result = { state, sha: req.basis.sha };
			} else {
				const basis = req.basis;
				if (!basis || !req.check) throw new Error("先准备目标并完成本轮最小验证");
				if (params.operation === "steer" && "task" in basis && phase === "EXECUTE") {
					result = requestReplan(project, {
						operation: "trim_steer",
						key: req.key,
						claim: req.claim,
						task: basis.task.task,
						snapshot: basis.task.snapshot,
						verification: req.check,
						remaining: params.remaining,
						stop: params.stop,
					});
					if (result.ok !== true) throw new Error(String(result.reason));
				} else if (params.operation === "compact_context" && "sha" in basis && params.summary && !req.task) {
					const bytes = Buffer.byteLength(params.summary, "utf8");
					if (bytes > summaryLimitBytes) {
						throw new Error(
							`摘要是 ${bytes} 字节，超过 ${summaryLimitBytes} 字节。保留四个必需段落，删去重复背景和长证据原文后直接重试。`,
						);
					}
					const compact = compactPmState(project, req.key, req.claim, basis.sha, params.summary);
					const error = compact.error?.message ?? compact.stderr.trim();
					if (
						compact.status !== 0 &&
						!error.includes("Compaction must reduce pm-state.md and fit within 16 KiB")
					) {
						throw new Error(error || "PM 状态压缩器未完成。");
					}
					result =
						compact.status === 0
							? { state: "compacted", output: compact.stdout.trim(), transcript: "queued" }
							: { state: "pm-state-kept", reason: error, transcript: "queued" };
					req.contextApplied = true;
					ctx.requestCompaction({
						onError: (error) => ctx.ui.notify(`pi 上下文压缩未完成：${error.message}`, "warning"),
					});
				} else {
					throw new Error("操作与已验证的 trim 目标不匹配");
				}
				req.changed = true;
				req.basis = undefined;
				req.check = undefined;
			}
			return { content: [{ type: "text", text: JSON.stringify(result) }], details: result };
		},
	});

	pi.on("agent_end", (_event, ctx) => {
		if (pending && !pending.changed) ctx.ui.notify("本轮 trim 未写入变更。", "info");
		else if (pending && !pending.task && !pending.contextApplied) {
			ctx.ui.notify("本轮已收敛工作，key 接续上下文仍待压缩。", "warning");
		}
		pending = undefined;
	});

	return (args, ctx) => {
		if (!ctx.isIdle() || pending || (args && !taskName.test(args))) {
			ctx.ui.notify("请在 PM 窗口空闲时运行 /mw trim [task]。", "warning");
			return;
		}
		try {
			const claim = windowClaim();
			const own = index.readAll().filter((row) => row.status === "active" && row.claimId === claim);
			const watched = watchedKey()?.trim();
			const selected = watched
				? own.find((row) => normalizeKey(row.key) === normalizeKey(watched))
				: own.length === 1
					? own[0]
					: undefined;
			if (!selected || keyNameRefusal(selected.key)) throw new Error("请先选择当前窗口认领的 key。");
			const req: TrimRequest = { key: selected.key, claim, changed: false, contextApplied: false };
			const phase = owner(req);
			if (phase !== "EXECUTE" && (phase !== "VERIFY" || args)) throw new Error("当前 key 不在可 trim 的阶段。");
			const inventory = args
				? prepareTask(req, args)
				: requestReplan(project, { operation: "trim_inventory", key: req.key, claim });
			if (inventory.ok !== true) throw new Error(String(inventory.reason));
			if (args && req.basis && "task" in req.basis) {
				if (req.basis.task.status !== "running") throw new Error("该任务当前没有正在运行的 Worker。");
				req.task = req.basis.task.task;
			}
			pending = req;
			const tools = pi.getActiveTools();
			if (!tools.includes("trim_progress")) pi.setActiveTools([...tools, "trim_progress"]);
			pi.sendUserMessage(
				[
					`用户手动触发 /mw trim。仅处理当前 key ${JSON.stringify(req.key)}${req.task ? ` 的任务 ${JSON.stringify(req.task)}` : ""}。`,
					`当前状态 ${JSON.stringify(inventory)}`,
					"按需读取卡片、证据和进度。每个改动目标先准备，再用 bash 实际执行能证明拟保留路径或复用产物的最小检查；失败则修正或换方向并重验。",
					"范围允许且验证通过后直接推进。正在运行且原卡仍适用时用 trim_progress steer，写清继续完成的工作与停止的可选探索。未开始或以非成功状态结束的工作如需改卡，先用 trim_progress prepare_task，再复用 replan_tasks preview/apply 和现有裁决。保留 AC、FLOW、VC、必要依赖和证据。不要手改卡或 steer 文件。",
					...(req.task
						? []
						: [
								"先从接续记录和上面的在途清单确定下一项必要交付。仅在发现具体改卡目标后 inspect 那项任务。按行读取所需计划或证据片段，沿用已确认的历史结论。工作收敛后用 trim_progress prepare_context，做最小核对并调用 compact_context。",
								"摘要以 4 KiB 为目标，硬上限为 8192 UTF-8 字节，汉字通常占三个字节。依次用二级标题 Notes、Task Status、Decisions、Evidence Ledger，每节至少一条。记录剩余交付、有效取舍、在途任务、阻塞、下一步和证据路径，区分自验、独立复核与待验证。省去重复历史、证据原文、机器字段、PASS 标记和外层代码围栏。",
							]),
					"报告实际结果。已排队的 Worker 收窄消息和已被 Worker 消费的消息要区分。",
				].join("\n"),
			);
		} catch (error) {
			pending = undefined;
			ctx.ui.notify(error instanceof Error ? error.message : String(error), "warning");
		}
	};
}
