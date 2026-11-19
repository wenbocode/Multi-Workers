import { createHash, randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { ExtensionAPI, ExtensionContext } from "../../../core/extensions/types.ts";
import { IndexStore, keyNameRefusal, normalizeKey } from "../shared/index-store.ts";

const KIND = "mw:codex-desktop-direction";
const UUID = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
const MAX_AGE = 15_000;

/** Closed sender-origin label for MW/pi limited follow-up. It is a display and
 *  idempotence fact only: it carries no duty, stage or DP authority. */
export const MW_FOLLOWUP_SOURCE = "mw-followup";
export type PmChannelSource = typeof MW_FOLLOWUP_SOURCE;

export interface DutyEnvelope {
	shift: string;
	until: number;
	stopHash: string;
}

export function currentDutyRequest(cwd: string, key: string, value: unknown) {
	if (!value || typeof value !== "object") return false;
	const { shift, until, stopHash } = value as Partial<DutyEnvelope>;
	if (!shift || !/^[a-z0-9-]{1,80}$/.test(shift) || typeof until !== "number" || !(Date.now() < until)) return false;
	const directory = path.join(cwd, ".agenticdoc", key, "duty", shift);
	if (fs.existsSync(path.join(directory, "STOP"))) return false;
	const current = path.join(directory, "current.json");
	return fs.existsSync(current)
		? createHash("sha256").update(fs.readFileSync(current)).digest("hex") === stopHash
		: stopHash === "missing";
}

function sharingConflict(error: unknown) {
	return ["EPERM", "EACCES", "EBUSY"].includes((error as NodeJS.ErrnoException)?.code ?? "");
}

function windowFile(dir: string, key: string, claim: string) {
	return path.join(dir, normalizeKey(key), `${createHash("sha256").update(claim).digest("hex")}.json`);
}

function readJson(file: string) {
	return JSON.parse(fs.readFileSync(file, "utf8")) as Record<string, unknown>;
}

function writeJson(file: string, value: object, exclusive = false) {
	const tmp = `${file}.${randomUUID()}.tmp`;
	fs.writeFileSync(tmp, JSON.stringify(value), { flag: "wx", mode: 0o600 });
	try {
		if (exclusive) fs.linkSync(tmp, file);
		else {
			for (let attempt = 0; ; attempt++) {
				try {
					fs.renameSync(tmp, file);
					break;
				} catch (error) {
					if (!sharingConflict(error) || attempt === 3) throw error;
					Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 10 * (attempt + 1));
				}
			}
		}
	} finally {
		fs.rmSync(tmp, { force: true });
	}
}

/** A private per-user spool, outside worker workspaces. Callers run as the same trusted OS user. */
export class PmChannel {
	readonly dir: string;
	readonly index: IndexStore;
	constructor(project: string, home = os.homedir()) {
		const real = fs.realpathSync.native(project);
		const digest = createHash("sha256")
			.update(process.platform === "win32" ? real.toLowerCase() : real)
			.digest("hex");
		this.dir = path.join(home, ".mw-pm-channel", digest);
		this.index = new IndexStore(path.join(real, ".agenticdoc"));
	}

	status(key: string) {
		if (keyNameRefusal(key)) throw new Error("Invalid task key");
		const rows = this.index.readAuthorityRows().filter((r) => normalizeKey(r.key) === normalizeKey(key));
		if (rows.length !== 1) throw new Error("Missing or ambiguous task key");
		const [row] = rows;
		const base = { key: row.key, phase: row.phase, status: row.status, claim: row.claimId };
		const endpoint = windowFile(this.dir, key, row.claimId);
		if (row.status === "active" && fs.existsSync(endpoint)) {
			const window = readJson(endpoint);
			if (
				window.claim === row.claimId &&
				typeof window.binding === "string" &&
				UUID.test(window.binding) &&
				typeof window.at === "number" &&
				Date.now() >= window.at &&
				Date.now() - window.at < MAX_AGE
			) {
				return {
					...base,
					connected: true as const,
					binding: window.binding,
					activity: window.activity,
					session: window.session,
					observedAt: window.at,
				};
			}
		}
		return { ...base, connected: false as const, binding: undefined };
	}

	messagePath(key: string, binding: string, id: string, type: "request" | "receipt") {
		if (keyNameRefusal(key) || !UUID.test(binding) || !UUID.test(id))
			throw new Error("Invalid key, binding or message UUID");
		return path.join(this.dir, normalizeKey(key), binding, `${id}.${type}.json`);
	}

	/** Public path of the CURRENT window heartbeat for this claim. The reader
	 *  re-checks its claim/binding/session; a copy in a workspace is not this file. */
	windowPath(key: string, claim: string) {
		if (keyNameRefusal(key)) throw new Error("Invalid task key");
		return windowFile(this.dir, key, claim);
	}

	send(key: string, binding: string, id: string, text: string, duty?: DutyEnvelope, source?: PmChannelSource) {
		if (source !== undefined && source !== MW_FOLLOWUP_SOURCE) throw new Error("Invalid PM channel source");
		if (source !== undefined && duty !== undefined)
			throw new Error("MW follow-up source cannot be combined with a duty envelope");
		const state = this.status(key);
		if (!state.connected || state.binding !== binding)
			throw new Error("PM receiver unavailable or binding changed; refresh status");
		if (!text.trim() || Buffer.byteLength(text) > 16_384) throw new Error("Message must contain 1–16384 UTF-8 bytes");
		const file = this.messagePath(key, binding, id, "request");
		const message = {
			id,
			key: state.key,
			claim: state.claim,
			binding,
			text,
			duty,
			...(source === undefined ? {} : { source }),
			at: Date.now(),
		};
		try {
			writeJson(file, message, true);
		} catch (error) {
			if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
			const old = readJson(file);
			if (
				old.text !== text ||
				old.claim !== state.claim ||
				old.binding !== binding ||
				JSON.stringify(old.duty) !== JSON.stringify(duty) ||
				old.stage !== undefined ||
				old.source !== source
			)
				throw new Error("Message ID conflict");
		}
		return this.receipt(key, binding, id);
	}

	receipt(key: string, binding: string, id: string) {
		const file = this.messagePath(key, binding, id, "receipt");
		if (fs.existsSync(file)) return readJson(file);
		if (!fs.existsSync(this.messagePath(key, binding, id, "request"))) throw new Error("Unknown message");
		return { id, key, binding, state: "queued" };
	}
}

export function registerPmChannel(pi: ExtensionAPI, home?: string) {
	if (process.env.PI_WORKER_TASK !== undefined) return;
	let timer: NodeJS.Timeout | undefined;
	let active: { key: string; binding: string; session: string; spool: PmChannel } | undefined;
	let processing: { id: string; file: string; inContext: boolean; receivedAt: number } | undefined;
	let heartbeatFailureSince: number | undefined;
	let lastHeartbeatWarning = 0;
	const claim = `${os.hostname()}:${process.pid}`;

	function poll(ctx: ExtensionContext) {
		const spool = active?.spool ?? new PmChannel(ctx.cwd, home);
		const rows = spool.index.readAuthorityRows();
		const owned = rows.filter((r) => r.status === "active" && r.claimId === claim);
		const key = owned[0]?.key;
		if (
			owned.length !== 1 ||
			!key ||
			keyNameRefusal(key) ||
			rows.filter((r) => normalizeKey(r.key) === normalizeKey(key)).length !== 1
		) {
			active = undefined;
			processing = undefined;
			return;
		}
		const session = ctx.sessionManager.getSessionId();
		if (!active || active.key !== key || active.session !== session) {
			active = { key, binding: randomUUID(), session, spool };
			processing = undefined;
		}
		const { binding } = active;
		const dir = path.join(spool.dir, normalizeKey(key), binding);
		fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
		try {
			writeJson(windowFile(spool.dir, key, claim), {
				claim,
				binding,
				session,
				at: Date.now(),
				activity: ctx.isIdle() ? "idle" : "working",
			});
			heartbeatFailureSince = undefined;
		} catch (error) {
			if (!sharingConflict(error)) throw error;
			const now = Date.now();
			heartbeatFailureSince ??= now;
			if (now - heartbeatFailureSince >= MAX_AGE && now - lastHeartbeatWarning >= 60_000) {
				lastHeartbeatWarning = now;
				ctx.ui.notify(`MW PM channel heartbeat delayed: ${String(error)}`, "warning");
			}
			// The last published heartbeat stays intact. A previously addressed
			// request still belongs to this verified claim, binding and session.
		}
		if (processing || !ctx.isIdle() || ctx.hasPendingMessages()) return;
		for (const name of fs.readdirSync(dir).sort()) {
			if (!name.endsWith(".request.json")) continue;
			const id = name.slice(0, -".request.json".length);
			if (!UUID.test(id)) continue;
			const file = spool.messagePath(key, binding, id, "receipt");
			if (fs.existsSync(file)) continue;
			const req = readJson(path.join(dir, name));
			if (
				req.stage !== undefined ||
				(req.source !== undefined && (req.source !== MW_FOLLOWUP_SOURCE || req.duty !== undefined))
			) {
				writeJson(file, { id, key, binding, state: "rejected" }, true);
				continue;
			}
			if (
				req.id !== id ||
				req.binding !== binding ||
				req.key !== key ||
				req.claim !== claim ||
				(req.duty !== undefined && !currentDutyRequest(ctx.cwd, key, req.duty)) ||
				typeof req.text !== "string" ||
				!req.text.trim() ||
				Buffer.byteLength(req.text) > 16_384 ||
				typeof req.at !== "number" ||
				Date.now() - req.at > 3_600_000
			) {
				writeJson(file, { id, key, binding, state: "rejected" }, true);
				continue;
			}
			const receivedAt = Date.now();
			writeJson(
				file,
				{
					id,
					key,
					binding,
					session,
					claim,
					state: "received",
					receivedAt,
				},
				true,
			);
			processing = { id, file, receivedAt, inContext: false };
			pi.sendMessage(
				{
					customType: KIND,
					display: true,
					details: { id, binding },
					content: `[${req.source === MW_FOLLOWUP_SOURCE ? "MW/pi follow-up" : req.duty ? "MW 值守窗口" : "Codex 桌面窗口"} · ${key} · ${id}]\n${req.text}`,
				},
				{ triggerTurn: true },
			);
			break;
		}
	}

	pi.on("session_start", (_event, ctx) => {
		if (ctx.mode !== "tui" || !fs.existsSync(path.join(ctx.cwd, ".agenticdoc", "_index.parallel"))) return;
		const tick = () => {
			try {
				poll(ctx);
			} catch (error) {
				ctx.ui.notify(`MW PM channel: ${String(error)}`, "warning");
			}
		};
		tick();
		timer = setInterval(tick, 2500);
		timer.unref();
	});
	pi.on("context", (event) => {
		if (!processing || !active) return;
		const id = processing.id;
		const binding = active.binding;
		processing.inContext = event.messages.some(
			(m) =>
				m.role === "custom" &&
				m.customType === KIND &&
				typeof m.details === "object" &&
				m.details !== null &&
				"id" in m.details &&
				m.details.id === id &&
				"binding" in m.details &&
				m.details.binding === binding,
		);
	});
	pi.on("message_end", (event) => {
		if (!active || !processing?.inContext || event.message.role !== "assistant") return;
		const m = event.message;
		const observed = m.content.find((p) => p.type === "toolCall" || (p.type === "text" && p.text.trim()));
		const failed = m.stopReason === "error" || m.stopReason === "aborted";
		if (!observed && !failed) return;
		writeJson(processing.file, {
			id: processing.id,
			key: active.key,
			binding: active.binding,
			session: active.session,
			claim,
			state: failed ? "failed" : "started",
			receivedAt: processing.receivedAt,
			observedAt: Date.now(),
			observation:
				observed?.type === "toolCall"
					? observed.name
					: observed?.type === "text"
						? observed.text.slice(0, 400)
						: m.stopReason,
		});
		processing = undefined;
	});
	pi.on("agent_end", () => {
		if (!active || !processing) return;
		writeJson(processing.file, {
			key: active.key,
			binding: active.binding,
			session: active.session,
			claim,
			id: processing.id,
			receivedAt: processing.receivedAt,
			state: "unconfirmed",
			observedAt: Date.now(),
		});
		processing = undefined;
	});
	pi.on("session_shutdown", () => {
		clearInterval(timer);
		if (active) {
			const file = windowFile(active.spool.dir, active.key, claim);
			if (fs.existsSync(file) && readJson(file).binding === active.binding) fs.unlinkSync(file);
		}
		active = undefined;
		processing = undefined;
	});
}
