import { Type } from "typebox";
import type { ExtensionAPI, ExtensionCommandContext } from "../../../core/extensions/types.ts";
import type { IndexStore } from "../shared/index-store.ts";
import { getMwStatus, initMw, startMw, stopMw } from "../shared/mw-runner.ts";

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
			};
		},
	});
}

export function registerMwCommands(pi: ExtensionAPI, projectDir: string): void {
	pi.registerCommand("mw", {
		description: "Control mw background service: start / stop / status",
		handler: async (_args: string, ctx: ExtensionCommandContext) => {
			const sub = _args.trim().split(/\s+/)[0] ?? "status";

			if (sub === "init") {
				const result = initMw(projectDir);
				if (result.ok) {
					ctx.ui.notify("mw init complete — .agenticdoc/ .mw/ .pi/extensions/ created.", "info");
				} else {
					ctx.ui.notify(result.error, "error");
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

			ctx.ui.notify("Usage: /mw init|start|stop|status", "warning");
		},
	});
}
