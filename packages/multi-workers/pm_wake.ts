/** Observe the next stop for each supplied binding and queue one desktop follow-up. */
import { spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { setTimeout } from "node:timers/promises";
import { StopWatch } from "./pm_watch.ts";

const [directory, ...targets] = process.argv.slice(2);
const thread = process.env.CODEX_THREAD_ID;
if (!thread || !/^[a-f0-9-]{36}$/i.test(thread) || !directory || !targets.length || targets.length % 4) {
	throw new Error("Run in the supervising Codex chat: node pm_wake.ts EVIDENCE_DIR PROJECT KEY CLAIM BINDING [...]");
}
const evidence = resolve(directory, thread);
mkdirSync(evidence, { recursive: true });
const watches = [];
for (let i = 0; i < targets.length; i += 4) {
	const [project, key, claim, binding] = targets.slice(i, i + 4);
	if (!/^[a-z0-9-]+$/i.test(key) || !/^[a-f0-9-]{36}$/i.test(binding)) throw new Error("Invalid key or binding");
	watches.push(new StopWatch(project, key, claim, binding));
}
console.log(JSON.stringify({ thread, evidence, targets: watches.map(watch => ({ ...watch.target, ...watch.sample() })) }));
while (watches.length) {
	for (const watch of [...watches]) {
		const stem = join(evidence, watch.target.key + "-" + watch.target.binding);
		if (existsSync(stem + ".event.json")) {
			watches.splice(watches.indexOf(watch), 1);
			continue;
		}
		const event = watch.observe(performance.now());
		if (!event) continue;
		if (event.state !== "idle" && event.state !== "worker-lost") {
			console.error(JSON.stringify(event));
			if (event.state === "binding-changed" || event.state === "finished") watches.splice(watches.indexOf(watch), 1);
			continue;
		}
		const id = randomUUID();
		const message = `MW 本机监听自动通知（事件 ${id}）。${event.key} 于 ${event.at} 触发 ${event.state}。当前桌面聊天按 mw-codex-pm-event-wake 接续：复核原绑定和任务最新停点，决定并投递下一步，确认 PM 开始处理和推进证据，将回合及回执记入该 key。其他事件分别处理。`;
		try {
			writeFileSync(stem + ".event.json", JSON.stringify({ id, thread, event, message }, null, 2), { flag: "wx" });
		} catch (error) {
			if ((error as NodeJS.ErrnoException).code === "EEXIST") continue;
			throw error;
		}
		const queued = spawnSync("codex", ["queue", "--thread", thread, "--message", message, "--resume"], {
			encoding: "utf8", windowsHide: true, timeout: 20_000,
		});
		const result = { id, at: new Date().toISOString(), exit: queued.status, stdout: queued.stdout,
			stderr: queued.stderr, error: queued.error?.message };
		writeFileSync(stem + ".queue.json", JSON.stringify(result, null, 2), { flag: "wx" });
		console.log(JSON.stringify({ id, key: event.key, exit: queued.status }));
		watches.splice(watches.indexOf(watch), 1);
	}
	if (watches.length) await setTimeout(5000);
}
