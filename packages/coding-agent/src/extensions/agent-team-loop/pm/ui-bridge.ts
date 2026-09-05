import * as fs from "node:fs";
import * as path from "node:path";
import { Type } from "typebox";
import type { ExtensionAPI, ExtensionCommandContext } from "../../../core/extensions/types.ts";
import type { IndexStore } from "../shared/index-store.ts";
import type { DoctorJson } from "../shared/mw-runner.ts";
import { buildMw, doctorMw, getMwStatus, initMw, startMw, stopMw } from "../shared/mw-runner.ts";
import { SCRATCH_WORKERS_KEY, workerTaskDir } from "../shared/paths.ts";
import type { WorkerStore } from "../shared/worker-store.ts";
import { dispatchTask } from "./task-dispatcher.ts";

/** Owner key for a worker task: explicit key, else the active key, else _scratch. */
function resolveOwnerKey(indexStore: IndexStore, explicit: string | undefined): string {
	const k = (explicit ?? "").trim();
	if (k) return k;
	return indexStore.activeKey() ?? SCRATCH_WORKERS_KEY;
}

export function displaySummary(pi: ExtensionAPI, summary: string): void {
	pi.sendMessage({
		customType: "agent-team-loop:worker-summary",
		content: summary,
		display: true,
		details: summary,
	});
}

export function registerPmKeyCommands(pi: ExtensionAPI, indexStore: IndexStore): void {
	pi.registerCommand("pm-key", {
		description: "Manage PM keys: new / switch / list",
		handler: async (args: string, ctx: ExtensionCommandContext) => {
			const [sub, ...rest] = args.trim().split(/\s+/);
			const keyName = rest[0] ?? "";

			if (sub === "list") {
				const entries = indexStore.readAll();
				if (entries.length === 0) {
					ctx.ui.notify("No keys found.", "info");
					return;
				}
				const table = entries.map((e) => `${e.key} | ${e.status} | ${e.phase}`).join("\n");
				ctx.ui.notify(table, "info");
				return;
			}

			if (sub === "new") {
				if (!keyName) {
					ctx.ui.notify("Usage: /pm-key new <key-name>", "warning");
					return;
				}
				await indexStore.upsert({
					key: keyName,
					status: "active",
					phase: "SPEC",
					claimId: new Date().toISOString(),
					deps: "",
					desc: "",
					updated: new Date().toISOString(),
				});
				ctx.ui.notify(`Created key: ${keyName}`, "info");
				return;
			}

			if (sub === "switch") {
				if (!keyName) {
					ctx.ui.notify("Usage: /pm-key switch <key-name>", "warning");
					return;
				}
				const target = indexStore.findByKey(keyName);
				if (!target) {
					ctx.ui.notify(`Key not found: ${keyName}`, "error");
					return;
				}
				// Mark any other active key as idle before activating the target
				const now = new Date().toISOString();
				for (const e of indexStore.readAll()) {
					if (e.status === "active" && e.key !== keyName) {
						await indexStore.upsert({ ...e, status: "idle", updated: now });
					}
				}
				await indexStore.upsert({ ...target, status: "active", updated: now });
				ctx.ui.notify(`Switched to key: ${keyName}`, "info");
				return;
			}

			ctx.ui.notify("Usage: /pm-key new|switch|list [key-name]", "warning");
		},
	});
}

export function registerMwTools(pi: ExtensionAPI, projectDir: string): void {
	pi.registerTool({
		name: "mw_status",
		label: "mw_status",
		description:
			"Check whether the multi-worker background service (mw serve) is running. Returns PID if running, or 'not running' if stopped.",
		parameters: Type.Object({}),
		execute: async (_toolCallId, _params, _signal, _onUpdate, _context) => {
			const s = getMwStatus(projectDir);
			return {
				content: [
					{
						type: "text",
						text: s.running
							? `mw is running (PID ${s.pid}). Workers are being dispatched and monitored.`
							: "mw is not running. Workers will not be dispatched. Use /mw start or ask the user to start it.",
					},
				],
				details: undefined,
			};
		},
	});
}

/**
 * Register agent-callable tools for worker dispatch and task listing.
 * These complement the slash commands in registerWorkerCommands.
 */
export function registerWorkerTools(
	pi: ExtensionAPI,
	workerStore: WorkerStore,
	indexStore: IndexStore,
	agenticdocRoot: string,
): void {
	// dispatch_worker: create a task.md and immediately dispatch it to the worker queue.
	pi.registerTool({
		name: "dispatch_worker",
		label: "dispatch_worker",
		description:
			"Dispatch a task to a background worker agent. Creates .agenticdoc/<task_key>/task.md and queues it for execution by the mw worker service. Returns the task key on success.",
		parameters: Type.Object({
			task_key: Type.String({
				description:
					"Unique kebab-case key for this task (e.g. 'fix-login-bug', 'add-auth-endpoint'). Must be unique across tasks in this project.",
			}),
			description: Type.String({
				description: "Full task description and instructions for the worker agent.",
			}),
			cli: Type.Optional(
				Type.String({
					description:
						"Worker type: 'pi' (default, coding tasks), 'claude' (review/research), 'codex' (codex tasks).",
				}),
			),
			model: Type.Optional(
				Type.String({
					description: "Optional model override for this worker (e.g. 'claude-sonnet-4-5').",
				}),
			),
			key: Type.Optional(
				Type.String({
					description:
						"AgenticTask key owning this worker task. Default: the active key; falls back to _scratch when no key is active.",
				}),
			),
		}),
		execute: async (_toolCallId, params, _signal, _onUpdate, _context) => {
			const {
				task_key,
				description,
				cli = "pi",
				model,
				key,
			} = params as {
				task_key: string;
				description: string;
				cli?: string;
				model?: string;
				key?: string;
			};
			const ownerKey = resolveOwnerKey(indexStore, key);

			const validCli = ["pi", "claude", "codex"];
			if (!validCli.includes(cli)) {
				return {
					content: [{ type: "text", text: `Invalid cli '${cli}'. Must be one of: ${validCli.join(", ")}.` }],
					details: undefined,
				};
			}

			// Worker tasks live under {ownerKey}/workers/<task_key>/ (never at the
			// agenticdoc root - that namespace belongs to AgenticTask keys).
			const taskDir = workerTaskDir(agenticdocRoot, ownerKey, task_key);
			if (fs.existsSync(taskDir)) {
				return {
					content: [
						{
							type: "text",
							text: `Task '${task_key}' already exists at ${taskDir}. Choose a different task_key or check existing tasks with list_tasks.`,
						},
					],
					details: undefined,
				};
			}

			const typeField = cli === "codex" ? "codex" : cli === "claude" ? "review" : "coding";
			const provider = cli === "pi" ? "timi" : "";

			fs.mkdirSync(taskDir, { recursive: true });
			const taskMdPath = path.join(taskDir, "task.md");
			const frontmatter = model ? `type: ${typeField}\nmodel: ${model}\n` : `type: ${typeField}\n`;
			fs.writeFileSync(taskMdPath, `${frontmatter}\n${description}\n`, "utf8");

			await dispatchTask(
				{ taskKey: task_key, status: "pending", cli, provider, model: model ?? "", taskPath: taskMdPath },
				workerStore,
			);

			return {
				content: [
					{
						type: "text",
						text: `Dispatched worker '${task_key}' (type: ${cli}${model ? `, model: ${model}` : ""}) under key '${ownerKey}'. Task file: ${taskMdPath}. Check mw_status to confirm the service is running.`,
					},
				],
				details: undefined,
			};
		},
	});

	// list_tasks: return all tracked tasks and their current status.
	pi.registerTool({
		name: "list_tasks",
		label: "list_tasks",
		description:
			"List all worker tasks in this project with their current status (pending / running / done / failed / needs-clarification).",
		parameters: Type.Object({}),
		execute: async (_toolCallId, _params, _signal, _onUpdate, _context) => {
			const entries = workerStore.readAll();
			if (entries.length === 0) {
				return { content: [{ type: "text", text: "No tasks found." }], details: undefined };
			}
			const lines = entries.map(
				(e) => `${e.taskKey} | ${e.status} | ${e.cli}${e.model ? ` | model: ${e.model}` : ""}`,
			);
			return { content: [{ type: "text", text: lines.join("\n") }], details: undefined };
		},
	});
}

/**
 * Spawn a worker directly from the pi window.
 * Usage: /worker <claude|codex|pi> [--model <id>] <task description>
 */
export function registerWorkerCommands(
	pi: ExtensionAPI,
	workerStore: WorkerStore,
	indexStore: IndexStore,
	agenticdocRoot: string,
): void {
	const USAGE = "Usage: /worker <claude|codex|pi> [--model <id>] [--key <name>] <task description>";
	pi.registerCommand("worker", {
		description: "Spawn a worker: /worker <claude|codex|pi> [--model <id>] <task description>",
		handler: async (args: string, ctx: ExtensionCommandContext) => {
			const parts = args.trim().split(/\s+/);
			const cli = (parts[0] ?? "").toLowerCase();

			// Optional `--model <id>` and `--key <name>` flags right after the cli;
			// everything else is the description.
			let idx = 1;
			let model = "";
			let keyArg = "";
			while (parts[idx] === "--model" || parts[idx] === "--key") {
				if (parts[idx] === "--model") {
					model = parts[idx + 1] ?? "";
					idx += 2;
					if (!model) {
						ctx.ui.notify(USAGE, "warning");
						return;
					}
				} else {
					keyArg = parts[idx + 1] ?? "";
					idx += 2;
					if (!keyArg) {
						ctx.ui.notify(USAGE, "warning");
						return;
					}
				}
			}
			const description = parts.slice(idx).join(" ");

			const validCli = ["claude", "codex", "pi"];
			if (!validCli.includes(cli)) {
				ctx.ui.notify(USAGE, "warning");
				return;
			}
			if (!description) {
				ctx.ui.notify("Task description is required.", "warning");
				return;
			}

			// Map CLI to task.md type field (must match pickWorkerRoute mapping)
			const typeField = cli === "codex" ? "codex" : cli === "claude" ? "review" : "coding";
			const provider = cli === "pi" ? "timi" : "";

			// Create task directory and task.md under {ownerKey}/workers/ (persist
			// model: so it's visible + re-parseable)
			const taskKey = `manual-${Date.now()}`;
			const ownerKey = resolveOwnerKey(indexStore, keyArg);
			const taskDir = workerTaskDir(agenticdocRoot, ownerKey, taskKey);
			fs.mkdirSync(taskDir, { recursive: true });
			const taskMdPath = path.join(taskDir, "task.md");
			const frontmatter = model ? `type: ${typeField}\nmodel: ${model}\n` : `type: ${typeField}\n`;
			fs.writeFileSync(taskMdPath, `${frontmatter}\n${description}\n`, "utf8");

			// Dispatch directly to _workers.parallel
			await dispatchTask({ taskKey, status: "pending", cli, provider, model, taskPath: taskMdPath }, workerStore);

			ctx.ui.notify(
				`Dispatched ${cli} worker (${taskKey}) under key '${ownerKey}'${model ? ` [model: ${model}]` : ""}.`,
				"info",
			);
		},
	});
}

/** Format a doctor JSON report as a readable Chinese summary (same data as
 * the CLI text output — the TS side never re-implements checks, AC-007). */
export function formatDoctorReport(report: DoctorJson, fix: boolean): string {
	const lines: string[] = [];
	const svc = report.service;
	lines.push(svc?.running ? `服务: 运行中 (PID ${svc.pid ?? "?"})` : "服务: 未运行");

	const proxyParts = (report.proxy ?? []).map(
		(p) => `${p.route ?? "?"}/${p.port ?? "?"} ${p.listening ? "监听中" : "未监听"}`,
	);
	if (proxyParts.length > 0) lines.push(`代理端口: ${proxyParts.join("; ")}`);

	const orphan = report.orphan_proxy;
	if (orphan?.detected) {
		const ports = (orphan.ports ?? []).map((p) => `${p.port} (PID ${(p.owner_pids ?? []).join(",") || "?"})`);
		lines.push(`孤儿代理: ${ports.join("; ")}（mw 未运行但端口被占，可启动 mw 接管或处置占用进程）`);
	}

	const log = report.launcher_log;
	if (log?.exists) {
		lines.push(`launcher 日志: ${log.error_count ?? 0} 个错误行${log.fatal ? "（含 FATAL）" : ""}`);
	} else {
		lines.push("launcher 日志: 无日志文件");
	}

	const queue = report.queue;
	lines.push(
		`队列: ${queue?.non_terminal?.length ?? 0} 个进行中任务，${
			queue?.stale_count ?? 0
		} 个 stale，${queue?.archived_total ?? 0} 条已归档`,
	);

	const credParts = (report.credentials?.routes ?? []).map(
		(r) => `${r.route ?? "?"} ${r.available ? "可用" : "缺凭证"}`,
	);
	if (credParts.length > 0) lines.push(`路由凭证: ${credParts.join("; ")}（以 mw 进程 env 为准）`);

	const bundle = report.bundle;
	if (bundle?.available) {
		lines.push(bundle.stale ? "扩展 bundle: 源码较新，建议 /mw build 重建" : "扩展 bundle: 最新");
	}

	if (fix) {
		const applied = report.fix?.applied;
		lines.push(Array.isArray(applied) && applied.length > 0 ? `已自动修复: ${applied.join("; ")}` : "无可自动修复项");
	}

	const summary = report.summary;
	if (summary?.healthy) {
		lines.push("整体: 健康");
	} else {
		const issues = Array.isArray(summary?.issues) ? (summary?.issues as string[]) : [];
		lines.push(issues.length > 0 ? `整体: ${issues.length} 个问题 — ${issues.join("; ")}` : "整体: 未知");
	}
	const suggestions = Array.isArray(summary?.suggestions) ? (summary?.suggestions as string[]) : [];
	for (const s of suggestions) lines.push(`建议: ${s}`);
	return lines.join("\n");
}

export function registerMwCommands(pi: ExtensionAPI, projectDir: string): void {
	pi.registerCommand("mw", {
		description: "Control mw: build / init / start / stop / status",
		handler: async (_args: string, ctx: ExtensionCommandContext) => {
			const sub = _args.trim().split(/\s+/)[0] ?? "status";

			if (sub === "build") {
				ctx.ui.notify("Rebuilding extension bundle (bash-free)…", "info");
				const r = buildMw();
				if (r.ok) {
					ctx.ui.notify(`mw build OK — reinstalled globally. Restart pi windows to load it.\n${r.output}`, "info");
				} else {
					ctx.ui.notify(`mw build failed: ${r.error}`, "error");
				}
				return;
			}

			if (sub === "init") {
				const result = initMw(projectDir);
				if (result.ok) {
					ctx.ui.notify("mw init complete — .agenticdoc/ .mw/ .pi/extensions/ created.", "info");
				} else {
					ctx.ui.notify(result.error, "error");
				}
				return;
			}

			if (sub === "doctor") {
				const fix = _args.trim().split(/\s+/)[1]?.toLowerCase() === "fix";
				const r = doctorMw(projectDir, fix);
				if (r.ok) {
					ctx.ui.notify(formatDoctorReport(r.report, fix), "info");
				} else {
					ctx.ui.notify(`mw doctor 执行失败: ${r.error}`, "error");
				}
				return;
			}

			if (sub === "status") {
				const s = getMwStatus(projectDir);
				ctx.ui.notify(s.running ? `mw running (PID ${s.pid})` : "mw not running", "info");
				return;
			}

			if (sub === "start") {
				const s = getMwStatus(projectDir);
				if (s.running) {
					ctx.ui.notify(`mw already running (PID ${s.pid})`, "info");
					return;
				}
				const ok = startMw(projectDir);
				ctx.ui.notify(
					ok ? "mw starting in background…" : "Could not find mw.py — set MW_PY env var.",
					ok ? "info" : "error",
				);
				return;
			}

			if (sub === "stop") {
				const s = getMwStatus(projectDir);
				if (!s.running) {
					ctx.ui.notify("mw is not running", "info");
					return;
				}
				stopMw(projectDir);
				ctx.ui.notify("mw stop signal sent", "info");
				return;
			}

			ctx.ui.notify("Usage: /mw build|init|start|stop|status|doctor [fix]", "warning");
		},
	});
}
