/** Continuous desktop PM supervision. Start with a config pinned to the supervising thread. */
import { spawn, spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { appendFileSync, existsSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { dirname, join, resolve } from "node:path";
import { setTimeout } from "node:timers/promises";
import { StopWatch } from "./pm_watch.ts";
import { lockDutyTarget } from "./pm_duty_lease.ts";

type Pin = { project: string; key: string; claim: string; binding: string; session: string };
type Status = ReturnType<StopWatch["sample"]>["state"];
type Notice = { id: string; kind: Status; at: number; attempts: number; lastTry: number; queued: boolean };
type Journal = { binding: string; stop?: Notice; health?: Notice };
type Deliver = (message: string) => { accepted: boolean; detail: string };

export class Duty {
	readonly directory: string;
	private journal: Journal;
	private last?: Status;
	private since = 0;

	constructor(pin: Pin, directory: string) {
		this.directory = directory;
		mkdirSync(directory, { recursive: true });
		const file = join(directory, "state.json");
		this.journal = existsSync(file) ? JSON.parse(readFileSync(file, "utf8")) : { binding: pin.binding };
	}

	get binding() { return this.journal.binding; }

	private save() {
		const tmp = join(this.directory, randomUUID() + ".tmp");
		try {
			writeFileSync(tmp, JSON.stringify(this.journal), { flag: "wx" });
			renameSync(tmp, join(this.directory, "state.json"));
		} finally {
			rmSync(tmp, { force: true });
		}
	}

	rebind(binding: string) {
		this.journal = { binding };
		this.last = undefined;
		this.save();
	}

	tick(status: Status, now: number, pin: Pin, deliver: Deliver, startedAt?: number) {
		if (this.last !== status) { this.last = status; this.since = now; }
		const healthy = ["working", "waiting-for-worker", "idle", "worker-lost"].includes(status);
		const busy = status === "working" || status === "waiting-for-worker";
		const stop = this.journal.stop;
		// A short PM turn can finish between polls. Its actual receipt also proves rearming.
		const missedTurn = stop && startedAt !== undefined && startedAt >= stop.at && !busy;
		if ((healthy && this.journal.health) || (busy && stop) || (healthy && missedTurn)) {
			if (healthy) delete this.journal.health;
			if (busy || missedTurn) delete this.journal.stop;
			if (missedTurn) this.since = now;
			this.save();
		}
		if (busy || now - this.since < 45_000) return;
		const slot = healthy ? "stop" : "health";
		let notice = this.journal[slot];
		if (!notice || notice.kind !== status) {
			notice = { id: randomUUID(), kind: status, at: now, attempts: 0, lastTry: 0, queued: false };
			this.journal[slot] = notice;
			this.save();
		}
		// Once the chat acknowledges an external wait, stay quiet for this episode.
		if (existsSync(join(this.directory, notice.id + ".handled.json"))) return;
		const delay = notice.queued ? 15 * 60_000 : Math.min(120_000, 5000 * 2 ** Math.min(notice.attempts, 5));
		if (notice.attempts && now - notice.lastTry < delay) return;
		notice.lastTry = now;
		notice.attempts++;
		this.save();
		const message = `MW 连续值守自动事件 ${notice.id}。项目 ${pin.project}，key ${pin.key}，claim ${pin.claim}，binding ${this.binding}，状态 ${status}，时间 ${new Date(notice.at).toISOString()}。当前桌面聊天按 mw-codex-pm-overnight 接续：核对原窗、最新产物、在途 worker 及同 ID 回执。可推进时自行裁决写面和预算，使用本事件 ID 只发一次方向，确认原 PM 开始工作并留证。若已完成、明确人工停止、外部等待或连接异常，按实处理。处理结果写入 ${join(this.directory, notice.id + ".handled.json")}，然后让聊天空闲。常驻监听自动接续下一轮。`;
		const result = deliver(message);
		notice.queued = result.accepted;
		appendFileSync(join(this.directory, "events.jsonl"), JSON.stringify({ ...notice, pin, binding: this.binding, result }) + "\n");
		this.save();
	}

	get stopId() { return this.journal.stop?.id; }
}

if (import.meta.main && process.argv[2] === "--supervise") {
	for (;;) {
		const child = spawn(process.execPath, [process.argv[1], resolve(process.argv[3])], { stdio: "inherit", windowsHide: true });
		const exit = await new Promise<number | null>((done, fail) => { child.once("exit", done); child.once("error", fail); });
		if (exit === 0) break;
		console.error(new Date().toISOString(), "Restarting PM monitor after exit", exit);
		await setTimeout(5000);
	}
} else if (import.meta.main) {
	const configFile = resolve(process.argv[2]);
	const config: { thread: string; targets: Pin[] } = JSON.parse(readFileSync(configFile, "utf8"));
	if (process.env.CODEX_THREAD_ID !== config.thread || !/^[a-f0-9-]{36}$/i.test(config.thread)) throw Error("Thread mismatch");
	const root = join(dirname(configFile), "evidence", "continuous");
	mkdirSync(root, { recursive: true });
	// OS releases the singleton on exit, including a crash. No stale PID-file takeover.
	const lock = createServer(socket => socket.end());
	const pipe = process.platform === "win32" ? "\\\\.\\pipe\\mw-pm-duty-" + config.thread : join(root, "duty.sock");
	lock.on("error", error => { console.error(String(error)); process.exit((error as NodeJS.ErrnoException).code === "EADDRINUSE" ? 0 : 1); });
	await new Promise<void>(ready => lock.listen(pipe, ready));
	const targets = config.targets.map(pin => {
		if (!/^[a-z0-9-]+$/i.test(pin.key)) throw Error("Invalid PM key");
		const duty = new Duty(pin, join(root, pin.key));
		return { pin, duty, watch: new StopWatch(pin.project, pin.key, pin.claim, duty.binding) };
	});
	const targetLocks = [];
	for (const { watch, pin } of targets) targetLocks.push(await lockDutyTarget(watch.channel.dir, pin.key));
	writeFileSync(join(root, "runner.json"), JSON.stringify({ pid: process.pid, thread: config.thread, started: new Date(), targets: config.targets }));
	function pollTarget(target: (typeof targets)[number]) {
			const { pin, duty } = target;
			let sample = target.watch.sample();
			if (sample.state === "binding-changed") {
				const status = target.watch.channel.status(pin.key);
				if (status.connected && status.claim === pin.claim && status.session === pin.session && status.binding && status.binding !== duty.binding) {
					duty.rebind(status.binding);
					target.watch = new StopWatch(pin.project, pin.key, pin.claim, status.binding);
					sample = target.watch.sample();
				}
			}
			let startedAt: number | undefined;
			if (duty.stopId && sample.state === "idle") {
				const receipt = target.watch.channel.messagePath(pin.key, duty.binding, duty.stopId, "receipt");
				if (existsSync(receipt)) {
					const r = target.watch.channel.receipt(pin.key, duty.binding, duty.stopId);
					if (r.state === "started" && r.session === pin.session && typeof r.observedAt === "number") startedAt = r.observedAt;
				}
			}
			duty.tick(sample.state, Date.now(), pin, message => {
				const queued = spawnSync("codex", ["queue", "--thread", config.thread, "--message", message, "--resume"], {
					encoding: "utf8", timeout: 20_000, windowsHide: true,
				});
				return { accepted: queued.status === 0 && Boolean(queued.stdout?.includes(config.thread)), detail: [queued.stdout, queued.stderr, queued.error?.message].filter(Boolean).join(" ").trim() };
			}, startedAt);
	}
	const errors = new Map<string, string>();
	while (!existsSync(join(root, "STOP"))) {
		for (const target of targets) {
			try {
				pollTarget(target);
				errors.delete(target.pin.key);
			} catch (error) {
				if (errors.get(target.pin.key) !== String(error)) console.error(new Date().toISOString(), target.pin.key, error);
				errors.set(target.pin.key, String(error));
			}
		}
		await setTimeout(5000);
	}
	lock.close();
	for (const server of targetLocks) server.close();
}
