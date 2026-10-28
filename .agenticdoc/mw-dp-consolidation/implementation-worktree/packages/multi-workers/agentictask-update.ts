/**
 * /update-agentictask — 在任意 pi 窗口一键更新本项目的 AgenticTask 框架安装。
 *
 * 行为：调用 Multi-Workers 的 mw.py init <当前项目>（幂等：存量 .agenticdoc 状态
 * skip-if-exists 零触碰）。框架源解析（_resolve_framework_source）：
 * --sync-agentictask > mw 检出自身的 .agents/skills/agentic-task（开发机活工作仓库，
 * 始终最新，含未提交状态）> .tmp 缓存兜底（缺失时自动 clone）。已装项目
 * 的 skill 克隆会被 pull --ff-only 刷新。
 * 完成后提示 /reload 刷新 SKILL.md 摘要与 goal.ts 门禁（脚本/文档行为即时生效，无需 reload）。
 *
 * mw.py 定位：MW_PY 环境变量 > 同目录 .mw-py-path sidecar（mw setup / mw build
 * --install 写入，与 agent-team-loop 的 findMwPy 同源）。
 *
 * 本文件由 mw setup 安装到 pi 全局扩展目录，机器无关 —— 不要在这里写死路径。
 */

import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

function findMwPy(): string | null {
	const envPath = process.env.MW_PY;
	if (envPath && fs.existsSync(envPath)) return envPath;
	try {
		// Sidecar next to this file, written by mw setup / mw build --install.
		const sidecar = path.join(path.dirname(fileURLToPath(import.meta.url)), ".mw-py-path");
		if (fs.existsSync(sidecar)) {
			const recorded = fs.readFileSync(sidecar, "utf8").trim();
			if (recorded && fs.existsSync(recorded)) return recorded;
		}
	} catch {
		// Unreadable sidecar → fall through
	}
	return null;
}

function run(command: string, args: string[], cwd: string): Promise<{ code: number; out: string }> {
	return new Promise((resolve) => {
		const p = spawn(command, args, { cwd, shell: true });
		let out = "";
		p.stdout.on("data", (d: Buffer) => (out += d.toString()));
		p.stderr.on("data", (d: Buffer) => (out += d.toString()));
		p.on("error", (err) => resolve({ code: -1, out: String(err) }));
		p.on("close", (code) => resolve({ code: code ?? -1, out }));
	});
}

function tail(text: string, maxLines: number): string {
	const lines = text.trimEnd().split("\n");
	return lines.length > maxLines ? `... (${lines.length - maxLines} lines omitted)\n` + lines.slice(-maxLines).join("\n") : text.trimEnd();
}

export default function agentictaskUpdateExtension(pi: ExtensionAPI) {
	pi.registerCommand("update-agentictask", {
		description: "Update the AgenticTask framework install in this project (mw init)",
		handler: async (_args, ctx) => {
			if (!ctx.hasUI) return;
			const mwPy = findMwPy();
			if (!mwPy) {
				ctx.ui.notify("mw.py not found (set MW_PY, or re-run mw setup to write .mw-py-path)", "error");
				return;
			}
			ctx.ui.notify("Updating AgenticTask framework (mw init)...", "info");
			const { code, out } = await run(
				"python",
				[JSON.stringify(mwPy), "init", "--project", JSON.stringify(ctx.cwd)],
				ctx.cwd,
			);
			ctx.ui.notify(
				`mw init exit=${code}\n${tail(out, 25)}\n\nScripts/docs are live now; run /reload to refresh the skill summary and goal gate.`,
				code === 0 ? "info" : "error",
			);
		},
	});
}
