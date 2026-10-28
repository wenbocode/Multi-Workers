/**
 * goal.md loader + write gate
 *
 * 唯一目标文件：.agenticdoc/goal.md（与 agent-team-loop 框架共用同一份）。
 *
 * 本文件由 `mw setup` / `mw build --install` 安装到 pi 全局扩展目录
 * （`~/.pi/agent/extensions/goal.ts`，见 mw.py::_goal_gate_install），
 * 是仓库外的安装副本的唯一来源 —— 机器无关，不要在这里写死路径。
 * 修改后：重跑 mw setup（或 mw build --install）刷新全局副本，pi 窗口 /reload 生效。
 *
 * - session_start: 读取该文件；存在则提示已加载，不存在则提醒用户创建。
 * - before_agent_start: 每轮把内容注入 system prompt，压缩/多轮后仍然生效，
 *   文件中途创建或修改也会在下一轮自动生效。
 * - tool_call: 写入门禁——goal.md 是低频变更的项目宪法。只有「会改动 goal.md」
 *   的 write/edit/bash 调用被拦：交互模式弹确认框，无 UI（worker/打印模式）
 *   直接阻断。纯读取（read 工具、cat/type/Get-Content、只读 python/node 脚本、
 *   grep/git log、把 goal.md 拷出去做备份）不触发门禁。
 *   正常修改路径：/goal 工作流或用户明确指示。
 *
 * bash 判定口径（2026-10-16 修订，mw-goal-gate-write-intent）：按「写意图」判定，
 * 而不是「命令里提到 goal.md」。旧口径把
 * `node -e '...readFileSync(".agenticdoc/goal.md")'`、
 * `python -c "print(Path('goal.md').stat())"` 这类只读命令也判成写入——worker
 * （无 UI）被直接阻断，交互窗口被弹确认框，即「读也被拦」。新口径按 shell 分段
 * （引号感知）逐段判定，只读形态一律放行；判定块见
 * GOAL-GATE-CLASSIFIER-BEGIN/END（块内不依赖 pi runtime，测试原样抽取执行）。
 */

import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { isToolCallEventType } from "@earendil-works/pi-coding-agent";

function goalFile(cwd: string): string {
	return path.join(path.resolve(cwd), ".agenticdoc", "goal.md");
}

/** 同一路径比较（win32 大小写不敏感）。 */
function samePath(a: string, b: string): boolean {
	const fold = (s: string) => (process.platform === "win32" ? s.toLowerCase() : s);
	return fold(path.normalize(a)) === fold(path.normalize(b));
}

function isGoalFile(p: string, cwd: string): boolean {
	try {
		const abs = path.resolve(cwd, p);
		const goal = goalFile(cwd);
		if (samePath(abs, goal)) return true;
		// junction/symlink 拼法：两边都 realpath 后再比一次（目标不存在则不算）。
		return samePath(fs.realpathSync(abs), fs.realpathSync(goal));
	} catch {
		return false;
	}
}

// GOAL-GATE-CLASSIFIER-BEGIN
// 纯 bash 写意图判定：只做文本判定，不依赖 fs/pi（测试从本文件原样抽取执行）。
// 段内规则：
//   1. 重定向目标是 goal.md（`> goal.md` / `>> .agenticdoc/goal.md` / `2> goal.md`）
//   2. 首词是覆盖/删除/移动/改名类动词，且段内出现 goal.md（cp 类只看目标位）
//   3. 原地编辑器（sed -i / perl -i / ruby -i ... goal.md）
//   4. git checkout|restore|reset|clean|apply|stash 涉及 goal.md（会回写工作树）
//   5. 内联代码（python/node/perl/ruby/awk/pwsh/powershell -c|-e|--eval|<<）
//      同时出现 goal.md 与写标记（write_text/writeFileSync/open(...,'w')/Set-Content/...）
// 其余（cat/type/Get-Content/只读脚本/grep/git log/diff/cp 出去）一律不算写入。

const GOAL_REF = /goal\.md(?![.\w])/i;

/** 重定向目标是 goal.md（含引号形态）。 */
const REDIRECT_TO_GOAL =
	/(?:^|[\s;&|(])\d?>>?\s*("[^"]*goal\.md(?![.\w])[^"]*"|'[^']*goal\.md(?![.\w])[^']*'|[^\s;&|>]*goal\.md(?![.\w]))/i;

/** 覆盖/删除/移动/改名类动词（首词命中时，段内出现 goal.md 即视为写入）。 */
const MUTATE_VERBS = new Set([
	"rm",
	"del",
	"erase",
	"rd",
	"rmdir",
	"mv",
	"move",
	"ren",
	"rename",
	"shred",
	"truncate",
	"unlink",
	"remove-item",
	"move-item",
	"rename-item",
	"set-content",
	"add-content",
	"clear-content",
	"out-file",
	"tee",
	"new-item",
]);

/** 复制类动词：只有 goal.md 位于「目标位」才算写入（`cp goal.md x` 是读）。 */
const COPY_VERBS = new Set(["cp", "copy", "copy-item", "rsync", "install", "xcopy", "robocopy", "scp"]);

/** 原地编辑（sed -i / perl -i / ruby -i ... goal.md）。 */
const IN_PLACE_EDIT =
	/\b(sed|perl|ruby)\b[^\n;&|]*\s-i(?:\.\w+)?\b[^\n;&|]*goal\.md(?![.\w])|\b(sed|perl|ruby)\b[^\n;&|]*\s--in-place\b[^\n;&|]*goal\.md(?![.\w])/i;

/** git 子命令会把 goal.md 的工作树内容改回来。 */
const GIT_WRITES_GOAL =
	/\bgit\b[^\n;&|]*\b(checkout|restore|reset|clean|apply|stash)\b[^\n;&|]*goal\.md(?![.\w])/i;

/** 内联解释器调用（`-c`/`-e`/`--eval`/heredoc）。 */
const INLINE_CODE_RE =
	/\b(python3?|node|deno|bun|perl|ruby|awk|pwsh|powershell)\b[^\n;&|]*(\s-c\b|\s-e\b|\s--eval\b|<<)/i;

/** 内联代码里的写标记（刻意不收裸 'w'/'a'，避免把只读脚本误判成写）。 */
const INLINE_WRITE_MARKER =
	/writefilesync|writefile|write_file|write_text|write_bytes|appendfile|appendfilesync|createwritestream|unlink|rmsync|rmtree|os\.remove|os\.rename|os\.replace|shutil\.(move|copy|copyfile|copy2)|truncate|open\([^)]*,\s*['"][^'"]*[wax][^'"]*['"]|set-content|add-content|out-file|remove-item|move-item|copy-item|rename-item|new-item/i;

/** 引号感知的 shell 分段（`;` `\n` `&&` `||` `|` 分段，引号内的分隔符不切）。 */
function splitSegments(cmd: string): string[] {
	const out: string[] = [];
	let cur = "";
	let quote: string | null = null;
	for (let i = 0; i < cmd.length; i++) {
		const ch = cmd[i] ?? "";
		if (quote !== null) {
			cur += ch;
			if (ch === "\\" && quote === '"') {
				const next = cmd[i + 1];
				if (next !== undefined) {
					cur += next;
					i++;
				}
				continue;
			}
			if (ch === quote) quote = null;
			continue;
		}
		if (ch === '"' || ch === "'") {
			quote = ch;
			cur += ch;
			continue;
		}
		const two = cmd.slice(i, i + 2);
		if (ch === ";" || ch === "\n" || two === "&&" || two === "||" || ch === "|") {
			out.push(cur);
			cur = "";
			if (two === "&&" || two === "||") i++;
			continue;
		}
		cur += ch;
	}
	out.push(cur);
	return out;
}

/** 段内首词（跳过 sudo/command/env/VAR=x/括号等前缀），小写化并去掉 .exe。 */
function firstVerb(segment: string): string | null {
	const tokens = segment.trim().split(/\s+/);
	for (const token of tokens) {
		const t = token.replace(/^[(&{]+/, "").replace(/["']+$/g, "");
		if (t === "" || t === "!") continue;
		if (t === "sudo" || t === "command" || t === "nohup" || t === "env" || t === "time") continue;
		if (/^[A-Za-z_][A-Za-z0-9_]*=/.test(t)) continue; // VAR=value
		return t.toLowerCase().replace(/\.exe$/, "");
	}
	return null;
}

/** 复制类动词的最后一个非 flag 操作数（目标位）是否 goal.md。 */
function copyDestinationIsGoal(segment: string): boolean {
	const tokens = segment.trim().split(/\s+/);
	const operands: string[] = [];
	for (let i = 1; i < tokens.length; i++) {
		const t = (tokens[i] ?? "").replace(/^["']|["']$/g, "");
		if (t === "") continue;
		// 开关形态：`-m 644` / cmd 的 `/y`（单段、纯字母），不是 POSIX 绝对路径。
		if (t.startsWith("-") || /^\/[A-Za-z?]+$/.test(t)) continue;
		operands.push(t);
	}
	const dest = operands[operands.length - 1];
	return dest !== undefined && GOAL_REF.test(dest);
}

function segmentWritesGoal(segment: string): boolean {
	if (!GOAL_REF.test(segment)) return false;
	if (REDIRECT_TO_GOAL.test(segment)) return true;
	if (IN_PLACE_EDIT.test(segment)) return true;
	if (GIT_WRITES_GOAL.test(segment)) return true;
	const verb = firstVerb(segment);
	if (verb !== null) {
		if (MUTATE_VERBS.has(verb)) return true;
		if (COPY_VERBS.has(verb) && copyDestinationIsGoal(segment)) return true;
	}
	if (INLINE_CODE_RE.test(segment) && INLINE_WRITE_MARKER.test(segment)) return true;
	return false;
}

/** 该 bash 命令是否会改动 goal.md（只读形态返回 false）。 */
function bashWritesGoalMd(cmd: string): boolean {
	if (typeof cmd !== "string" || cmd === "" || !GOAL_REF.test(cmd)) return false;
	return splitSegments(cmd).some(segmentWritesGoal);
}
// GOAL-GATE-CLASSIFIER-END

async function gateGoalWrite(ctx: ExtensionContext): Promise<{ block: true; reason: string } | undefined> {
	if (ctx.hasUI) {
		const ok = await ctx.ui.confirm(
			"goal.md 写入门禁",
			"goal.md 是低频变更的项目宪法，不应在工作流中被随手更新。确认本次修改？（正常路径：/goal 工作流或用户明确指示）",
		);
		if (ok) return undefined;
	}
	return {
		block: true,
		reason:
			"goal.md 是只读的项目目标锚点（低频变更）。修改需要用户确认：请在 PM 会话运行 /goal 工作流，或由用户明确指示后重试。",
	};
}

export default function goalExtension(pi: ExtensionAPI) {
	pi.on("session_start", async (_event, ctx) => {
		if (!ctx.hasUI) return;
		const file = goalFile(ctx.cwd);
		if (fs.existsSync(file)) {
			const content = fs.readFileSync(file, "utf-8");
			ctx.ui.notify(`已加载 .agenticdoc/goal.md（${content.length} 字符）`, "info");
		} else {
			ctx.ui.notify(
				"未找到 .agenticdoc/goal.md：建议创建并描述本项目目标（## Goal / ## Context / ## Key Constraints）",
				"warning",
			);
		}
	});

	pi.on("before_agent_start", async (event, ctx) => {
		const file = goalFile(ctx.cwd);
		if (!fs.existsSync(file)) {
			return {
				systemPrompt:
					event.systemPrompt +
					"\n\n## Project Goal\n\nNo .agenticdoc/goal.md exists. If the user asks about the project's goal, tell them .agenticdoc/goal.md is missing and offer to create it with them (sections: Goal / Context / Key Constraints).",
			};
		}
		const content = fs.readFileSync(file, "utf-8").replace(/^\uFEFF/, "").trim();
		if (!content) {
			return {
				systemPrompt:
					event.systemPrompt +
					"\n\n## Project Goal\n\n.agenticdoc/goal.md exists but is empty. If the user asks about the project's goal, ask the user to fill it in.",
			};
		}
		return {
			systemPrompt: event.systemPrompt + `\n\n## Project Goal (.agenticdoc/goal.md)\n\n${content}`,
		};
	});

	pi.on("tool_call", async (event, ctx) => {
		// 只拦 write/edit 直改 goal.md，以及会改动 goal.md 的 bash 命令；
		// 读取（read 工具、只读 bash）一律不问、不拦。
		if (
			(isToolCallEventType("write", event) || isToolCallEventType("edit", event)) &&
			isGoalFile(event.input.path, ctx.cwd)
		) {
			return await gateGoalWrite(ctx);
		}
		if (isToolCallEventType("bash", event) && bashWritesGoalMd(event.input.command ?? "")) {
			return await gateGoalWrite(ctx);
		}
	});
}
