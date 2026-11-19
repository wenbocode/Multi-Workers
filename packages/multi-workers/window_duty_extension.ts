import { createHash, randomUUID } from "node:crypto";
import {
	appendFileSync,
	existsSync,
	mkdirSync,
	readFileSync,
	renameSync,
	rmSync,
	statSync,
	writeFileSync,
} from "node:fs";
import type { Server } from "node:net";
import { hostname } from "node:os";
import { dirname, join, resolve } from "node:path";
import { Type } from "typebox";
import type {
	ExtensionAPI,
	ExtensionContext,
} from "../coding-agent/src/core/extensions/types.ts";
import { PmChannel } from "../coding-agent/src/extensions/agent-team-loop/pm/codex-channel.ts";
import { conductorClaimState } from "../coding-agent/src/extensions/agent-team-loop/shared/index-store.ts";
import { lockDutyTarget } from "./pm_duty_lease.ts";
import { StopWatch } from "./pm_watch.ts";
import { type Notice, parseShift, publishDutyFact, type Shift, WindowDuty } from "./window_duty.ts";
import { receiverSettings } from "./window_duty_setup.ts";

function unquote(path: string) {
	return path.replace(/^(["'])(.*)\1$/, "$2");
}

function explicitTarget(args: string, cwd: string) {
	const match = /^(?:"([^"]+)"|'([^']+)'|(\S+))\s+([a-z0-9][a-z0-9-]{0,79})$/.exec(args.trim());
	if (!match) return undefined;
	const project = resolve(cwd, match[1] ?? match[2] ?? match[3]);
	if (existsSync(project) && statSync(project).isFile()) return undefined;
	return { project, key: match[4] };
}

function dutySource(args: string, cwd: string, home?: string, expectedClaim?: string) {
	const input = args.trim();
	const file = resolve(cwd, unquote(input));
	if (!expectedClaim && existsSync(file) && statSync(file).isFile()) return { file };
	const match = /^(.+)\s+([a-z0-9][a-z0-9-]{0,79})$/.exec(input);
	if (!match) throw Error("Use <project path> <key> or an existing shift JSON file");
	const project = resolve(cwd, unquote(match[1].trim()));
	const key = match[2];
	const channel = new PmChannel(project, home);
	const live = channel.status(key);
	if (expectedClaim && live.claim !== expectedClaim) throw Error(`Original PM changed for ${project} / ${key}`);
	if (!live.connected || typeof live.session !== "string") return { disconnected: { project, key, channel, live } };
	const registration = join(channel.dir, key, "duty-registration.json");
	if (!existsSync(registration))
		return { watch: new StopWatch(project, key, live.claim, live.binding, home), session: live.session };
	const registered = readFileSync(registration, "utf8");
	const { file: registeredFile, sha256 } = JSON.parse(registered);
	if (typeof registeredFile !== "string" || typeof sha256 !== "string") throw Error("Invalid duty registration");
	const contents = readFileSync(registeredFile, "utf8");
	if (createHash("sha256").update(contents).digest("hex") !== sha256)
		throw Error("Registered shift card changed; register it again in the original PM");
	const shift = parseShift(contents);
	const target = shift.targets.find((t) => t.key === key && new PmChannel(t.project, home).dir === channel.dir);
	if (!target || target.claim !== live.claim || target.binding !== live.binding || target.session !== live.session)
		throw Error("Registered shift binding mismatch; register the current shift in the original PM");
	return { file: registeredFile, contents, shift: { ...shift, targets: [target] }, registration, registered };
}

export default function windowDutyExtension(pi: ExtensionAPI, home?: string) {
	if (process.env.PI_WORKER_TASK !== undefined) return;
	let stations: WindowDuty[] = [];
	let leases: Server[] = [];
	let timer: NodeJS.Timeout | undefined;
	let session: string | undefined;
	let opening = false;
	let generation = 0;
	let configFile = "";
	let original = "";
	let registration: { path: string; contents: string } | undefined;
	let audit = "";
	let activeNotice: Notice | undefined;
	let reporting: { shift: Shift; target: Shift["targets"][number] } | undefined;
	const warnings = new Map<string, string>();
	const busy = new Error("Duty window is already processing an event");
	let emit: (notice: Notice) => void;
	type DutyMode = "inactive" | "observation" | "shift" | "waiting";
	let mode: DutyMode = "inactive";
	let observer:
		| { watch: StopWatch; target: Pick<Shift["targets"][number], "project" | "key" | "claim" | "binding" | "session">; directory: string; observe: () => void }
		| undefined;
	let waiting: { project: string; key: string; claim: string; directory: string } | undefined;
	function close() {
		generation++;
		clearInterval(timer);
		timer = undefined;
		stations = [];
		session = undefined;
		activeNotice = undefined;
		reporting = undefined;
		registration = undefined;
		mode = "inactive";
		observer = undefined;
		waiting = undefined;
		for (const server of leases) server.close();
		leases = [];
		warnings.clear();
	}
	function record(data: object) {
		appendFileSync(audit, `${JSON.stringify({ at: new Date().toISOString(), session, ...data })}\n`);
	}
	function checkCard() {
		if (registration && readFileSync(registration.path, "utf8") !== registration.contents)
			throw Error("Original PM registered a different shift; repeat handoff");
		if (readFileSync(configFile, "utf8") !== original)
			throw Error("Shift card changed; stop and reconcile before sending.");
	}
	function sameTarget(requested: { project: string; key: string }) {
		const directory = new PmChannel(requested.project, home).dir;
		const pin =
			mode === "observation" ? observer : mode === "waiting" ? waiting : undefined;
		if (!pin || pin.directory !== directory) return false;
		const pinnedKey = "target" in pin ? pin.target.key : pin.key;
		return pinnedKey.toLowerCase() === requested.key.toLowerCase();
	}
	function dutyStatus(ctx: ExtensionContext) {
		if (session !== undefined && ctx.sessionManager.getSessionId() !== session) {
			close();
			ctx.ui.notify("Duty released: supervisor session changed", "warning");
		}
		const pinnedTargets: object[] = [];
		const observedStates: object[] = [];
		const outbox: unknown[] = [];
		const receipts: unknown[] = [];
		if (mode === "observation" && observer) {
			pinnedTargets.push({ ...observer.target });
			observedStates.push({
				project: observer.target.project,
				key: observer.target.key,
				...observer.watch.sample(),
			});
		} else if (mode === "shift") {
			for (const station of stations) {
				pinnedTargets.push({
					project: station.target.project,
					key: station.target.key,
					claim: station.target.claim,
					binding: station.target.binding,
					session: station.target.session,
					balance: station.balance,
				});
				observedStates.push({ key: station.target.key, ...station.watch.sample() });
				for (const entry of station.entries)
					if (entry.message) {
						outbox.push({ id: entry.id, stage: entry.stage });
						receipts.push({ id: entry.id, state: entry.receipt ?? null });
					}
			}
		} else if (mode === "waiting" && waiting)
			pinnedTargets.push({ project: waiting.project, key: waiting.key, claim: waiting.claim });
		return {
			mode,
			supervisorSession: session ?? null,
			pinnedTargets,
			observedStates,
			outbox,
			receipts,
			businessProgress: "unverified" as const,
			note: "Receipts and working activity are transport facts only; no engineering acceptance is verified here.",
		};
	}
	pi.registerCommand("duty-report-on", {
		description: "Attach this original PM as the producer of structured stops and progress",
		handler: async (args, ctx) => {
			if (ctx.mode !== "tui" || session || opening) throw Error("Requires the original interactive PM");
			const source = dutySource(args, ctx.cwd, home);
			if (source.disconnected)
				throw Error(`No connected original PM for ${source.disconnected.project} / ${source.disconnected.key}`);
			if (!source.file) throw Error("Register the authorized shift first with /duty-report-on <shift.json>");
			const contents = source.contents ?? readFileSync(source.file, "utf8");
			const shift = source.shift ?? parseShift(contents);
			const target = shift.targets.find(
				(t) => t.claim === `${hostname()}:${process.pid}` && t.session === ctx.sessionManager.getSessionId(),
			);
			if (!target) throw Error("Original PM binding mismatch");
			const channel = new PmChannel(target.project, home);
			const live = channel.status(target.key);
			if (
				!live.connected ||
				live.binding !== target.binding ||
				live.claim !== target.claim ||
				live.session !== target.session
			)
				throw Error("Original PM binding mismatch");
			if (!source.registration) {
				const pointer = join(channel.dir, target.key, "duty-registration.json");
				const tmp = `${pointer}.${randomUUID()}.tmp`;
				try {
					writeFileSync(
						tmp,
						JSON.stringify({ file: source.file, sha256: createHash("sha256").update(contents).digest("hex") }),
						{ flag: "wx", mode: 0o600 },
					);
					renameSync(tmp, pointer);
				} finally {
					rmSync(tmp, { force: true });
				}
			}
			reporting = { shift, target };
			ctx.ui.notify(`Duty reporting enabled for ${target.key}`, "info");
		},
	});
	pi.registerTool({
		name: "mw_duty_report",
		label: "Report duty stop or progress",
		description:
			"Original PM publishes a current stop or verified result. Supply a stable UUID and an existing evidence path relative to the target key. For result, use the direction ID and actual minutes spent.",
		parameters: Type.Object({
			id: Type.String(),
			state: Type.Union([
				Type.Literal("ready"),
				Type.Literal("waiting"),
				Type.Literal("done"),
				Type.Literal("stopped"),
				Type.Literal("result"),
			]),
			action: Type.String(),
			minutes: Type.Integer({ minimum: 0 }),
			reason: Type.String(),
			path: Type.String(),
			gate: Type.Union([Type.Literal("clear"), Type.Literal("blocked")]),
		}),
		async execute(_id, params, _signal, _update, ctx) {
			if (!reporting || reporting.target.session !== ctx.sessionManager.getSessionId())
				throw Error("Original PM has not enabled reporting");
			const { target, shift } = reporting;
			if (new PmChannel(target.project, home).status(target.key).binding !== target.binding)
				throw Error("Original binding changed");
			const file = publishDutyFact(shift, target, params);
			return { content: [{ type: "text", text: file }], details: { file } };
		},
	});
	pi.registerCommand("duty-off", {
		description: "Release this window's duty leases and retain pending deliveries",
		handler: async (_args, ctx) => {
			close();
			ctx.ui.notify("Duty released", "info");
		},
	});
	pi.registerCommand("duty-on", {
		description: "Supervise <project path> <key>, or accept a complete <shift.json>",
		handler: async function acceptDuty(args, ctx, expectedClaim?: string) {
			if (reporting || opening || ctx.mode !== "tui" || !args.trim())
				throw Error("Use a fresh interactive window and /duty-on <project path> <key> or /duty-on <shift.json>");
			if (session !== undefined) {
				if (ctx.sessionManager.getSessionId() !== session)
					throw Error("Supervisor session changed; run /duty-off and re-enable duty explicitly");
				const requested = explicitTarget(args, ctx.cwd);
				const shiftRepeat =
					!requested && mode === "shift" && resolve(ctx.cwd, unquote(args.trim())) === configFile;
				if (!(requested && sameTarget(requested)) && !shiftRepeat)
					throw Error("A different target or full shift requires /duty-off before /duty-on");
				ctx.ui.notify(`Duty already active: ${JSON.stringify(dutyStatus(ctx))}`, "info");
				return;
			}
			opening = true;
			const version = generation;
			const acquired: Server[] = [];
			try {
				const source = dutySource(args, ctx.cwd, home, expectedClaim);
				if (source.disconnected) {
					const { project, key, channel, live } = source.disconnected;
					if (live.claim === `${hostname()}:${process.pid}`) throw Error("Cannot supervise the current PM");
					if (expectedClaim || live.status !== "active" || conductorClaimState(live.claim) !== "live")
						throw Error(`No connected original PM for ${project} / ${key} (claim: ${live.claim})`);
					if (
						channel.index
							.readAuthorityRows()
							.filter((row) => row.status === "active" && row.claimId === live.claim).length !== 1
					)
						throw Error(`Original PM must own one active key to publish a receiver: ${live.claim}`);
					const setup = receiverSettings(project);
					if (setup.needsUpdate) {
						const accepted = await ctx.ui.confirm(
							"首次接入 MW 值守",
							`为 ${project} 的 ${key} 在 ${setup.file} 中登记 MW 收件和值守扩展？`,
						);
						if (!accepted || version !== generation) return;
						const latest = channel.status(key);
						if (latest.status !== "active" || latest.claim !== live.claim)
							throw Error("Original PM changed during setup");
						setup.install();
					}
					session = ctx.sessionManager.getSessionId();
					mode = "waiting";
					waiting = { project, key, claim: live.claim, directory: channel.dir };
					ctx.ui.notify(
						`等待 ${project} / ${key} 上线。请在原 PM 窗口空闲时执行 /reload；此窗会自动接班。/duty-off 可取消等待。`,
						"info",
					);
					timer = setInterval(() => {
						try {
							const status = channel.status(key);
							if (
								status.status !== "active" ||
								status.claim !== live.claim ||
								conductorClaimState(live.claim) !== "live"
							)
								throw Error(`原 PM 认领或进程已变化，请重新核对 ${project} / ${key}`);
							if (!status.connected) return;
							close();
							void acceptDuty(args, ctx, live.claim).catch((error: unknown) =>
								ctx.ui.notify(String(error), "error"),
							);
						} catch (error) {
							close();
							ctx.ui.notify(String(error), "error");
						}
					}, 2500);
					timer.unref();
					return;
				}
				if (source.watch) {
					const watch = source.watch;
					if (source.session === ctx.sessionManager.getSessionId()) throw Error("Cannot supervise the current PM");
					acquired.push(await lockDutyTarget(watch.channel.dir, watch.target.key));
					if (version !== generation) throw Error("Window changed during handoff");
					leases = acquired;
					session = ctx.sessionManager.getSessionId();
					mode = "observation";
					const observe = () => {
						const event = watch.observe(Date.now());
						if (event)
							ctx.ui.notify(
								`Duty observation: ${event.project} / ${event.key}: ${event.state} ${event.detail ?? ""}`.trim(),
								"info",
							);
					};
					observer = {
						watch,
						target: {
							project: watch.target.project,
							key: watch.target.key,
							claim: watch.target.claim,
							binding: watch.target.binding,
							session: String(source.session),
						},
						directory: watch.channel.dir,
						observe,
					};
					observe();
					timer = setInterval(observe, 5000);
					timer.unref();
					ctx.ui.notify(
						`Observing ${watch.target.project} / ${watch.target.key}. For delegated actions, register /duty-report-on <shift.json> in the original PM, then restart duty.`,
						"info",
					);
					return;
				}
				configFile = source.file;
				original = source.contents ?? readFileSync(configFile, "utf8");
				const shift = source.shift ?? parseShift(original);
				registration = source.registration ? { path: source.registration, contents: source.registered } : undefined;
				for (const t of shift.targets) {
					const channel = new PmChannel(t.project, home);
					const status = channel.status(t.key);
					if (status.connected && status.session === ctx.sessionManager.getSessionId())
						throw Error("Cannot supervise the current PM");
					acquired.push(await lockDutyTarget(channel.dir, t.key));
					acquired.push(await lockDutyTarget(channel.dir, t.key, "send"));
				}
				if (version !== generation) throw Error("Window changed during handoff");
				stations = shift.targets.map((t) => new WindowDuty(shift, t, home));
				session = ctx.sessionManager.getSessionId();
				mode = "shift";
				leases = acquired;
				audit = join(dirname(configFile), "duty-audit", `${shift.shift}.jsonl`);
				mkdirSync(dirname(audit), { recursive: true });
				emit = (notice) => {
					if (notice.kind === "duty" && (!ctx.isIdle() || ctx.hasPendingMessages())) throw busy;
					if (notice.kind === "user") ctx.ui.notify(notice.summary, "warning");
					else {
						activeNotice = notice;
						pi.sendMessage(
							{
								customType: "mw:duty-stop",
								display: true,
								details: notice,
								content:
									"MW 值守停点。仅裁决本事项；使用 mw_duty_decide 提交例外决定。诊断或人工接手请在此窗报告。\n" +
									notice.summary,
							},
							{ triggerTurn: true },
						);
					}
					record({ event: notice });
				};
				const poll = () => {
					for (const station of stations) {
						try {
							checkCard();
							station.poll(Date.now(), emit);
							warnings.delete(station.target.key);
						} catch (error) {
							if (error === busy || !ctx.isIdle() || ctx.hasPendingMessages()) continue;
							const message = String(error);
							if (warnings.get(station.target.key) !== message) {
								emit({
									kind: "duty",
									key: station.target.key,
									id: `${station.target.key}-reconcile`,
									summary: `Inspect the pinned window for ${station.target.key}: ${message}. Delivery is suspended.`,
								});
								warnings.set(station.target.key, message);
							}
						}
					}
				};
				record({
					handoff: stations.map((s) => ({ key: s.target.key, balance: s.balance, entries: s.entries.length })),
				});
				poll();
				timer = setInterval(poll, 5000);
				timer.unref();
				ctx.ui.notify(`Duty active for ${shift.targets.map((t) => t.key).join(", ")}`, "info");
			} catch (error) {
				for (const server of acquired) if (server.listening) server.close();
				stations = [];
				leases = [];
				session = undefined;
				mode = "inactive";
				observer = undefined;
				waiting = undefined;
				throw error;
			} finally {
				opening = false;
			}
		},
	});
	pi.registerTool({
		name: "mw_duty_status",
		label: "Report duty mode and observed state",
		description:
			"Report this window's actual duty mode (inactive/observation/shift/waiting), pinned targets, observed states and outbox/receipts. Business progress is always unverified here.",
		parameters: Type.Object({}),
		async execute(_id, _params, _signal, _update, ctx) {
			const status = dutyStatus(ctx);
			return { content: [{ type: "text", text: JSON.stringify(status) }], details: status };
		},
	});
	pi.registerTool({
		name: "mw_duty_decide",
		label: "Decide duty exception",
		description:
			"Approve or deny exactly the current delegated shift action. Approval sends only the direction fixed in the shift card.",
		parameters: Type.Object({
			key: Type.String(),
			id: Type.String(),
			approve: Type.Boolean(),
			reason: Type.String({ minLength: 1, maxLength: 1000 }),
		}),
		async execute(_id, params, _signal, _onUpdate, ctx) {
			const station = stations.find((s) => s.target.key === params.key);
			if (!session || session !== ctx.sessionManager.getSessionId() || !station)
				throw Error("No active duty lease for target");
			checkCard();
			if (!existsSync(station.input)) throw Error("Original stop withdrawn");
			station.poll(Date.now(), emit, params);
			const entry = station.entries.find((e) => e.id === params.id);
			if (entry?.approved !== params.approve)
				throw Error("Decision not applied; inspect current stop, budget, binding and receipt");
			return { content: [{ type: "text", text: JSON.stringify(entry) }], details: entry };
		},
	});
	pi.on("message_end", (event) => {
		if (session && activeNotice && event.message.role === "assistant")
			record({
				eventId: activeNotice.id,
				key: activeNotice.key,
				model: event.message.model,
				usage: event.message.usage,
			});
	});
	pi.on("agent_end", () => {
		activeNotice = undefined;
	});
	pi.on("session_shutdown", close);
}
