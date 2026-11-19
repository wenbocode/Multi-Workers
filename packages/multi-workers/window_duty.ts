import { createHash, randomUUID } from "node:crypto";
import {
	closeSync,
	existsSync,
	linkSync,
	mkdirSync,
	openSync,
	readFileSync,
	readSync,
	realpathSync,
	renameSync,
	statSync,
	unlinkSync,
	writeFileSync,
} from "node:fs";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { type Static, type TSchema, Type } from "typebox";
import { Check } from "typebox/value";
import { StopWatch } from "./pm_watch.ts";

const name = Type.String({ pattern: "^[a-z0-9][a-z0-9-]{0,79}$" });
const uuid = Type.String({ pattern: "^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$" });
const note = Type.String({ minLength: 1, maxLength: 1600 });
const minutes = Type.Integer({ minimum: 1, maximum: 1440 });
const rule = Type.Object({
	name,
	scope: note,
	direction: note,
	limit: minutes,
	exception: Type.Optional(Type.Boolean()),
	requires: Type.Optional(name),
	once: Type.Optional(Type.Boolean()),
});
const pin = Type.Object({
	project: note,
	key: name,
	claim: note,
	session: note,
	binding: uuid,
	minutes,
	rules: Type.Array(rule, { minItems: 1 }),
});
const shift = Type.Object({ shift: name, start: note, end: note, targets: Type.Array(pin, { minItems: 1 }) });
const proof = Type.Object({ path: note, sha256: Type.String({ pattern: "^[a-f0-9]{64}$" }) });
const snapshot = Type.Object({
	id: uuid,
	shift: name,
	claim: note,
	session: note,
	binding: uuid,
	state: Type.Union(["ready", "waiting", "stopped", "done"].map((s) => Type.Literal(s))),
	action: name,
	minutes: Type.Integer({ minimum: 0, maximum: 1440 }),
	reason: note,
	evidence: proof,
	gate: Type.Union([Type.Literal("clear"), Type.Literal("blocked")]),
});
const result = Type.Object({
	id: uuid,
	session: note,
	binding: uuid,
	evidence: proof,
	usedMinutes: Type.Integer({ minimum: 0 }),
});
export type Shift = Static<typeof shift>;
type Card = Static<typeof pin>;
type Stage = "decision" | "reserved" | "tracking" | "complete" | "handoff" | "denied" | "diagnosis";
interface Entry {
	id: string;
	fingerprint: string;
	hash: string;
	action: string;
	reason: string;
	evidence: string;
	minutes: number;
	charged: number;
	stage: Stage;
	message?: string;
	receipt?: string;
	at: number;
	sentAt?: number;
	approved?: boolean;
	decision?: string;
	progress?: string;
	inherited?: boolean;
	lastWake?: number;
	wakeCount?: number;
}
interface Ledger {
	card: string;
	entries: Entry[];
}
export interface Notice {
	kind: "duty" | "user";
	key: string;
	id: string;
	summary: string;
}

function digest(bytes: string | Buffer) {
	return createHash("sha256").update(bytes).digest("hex");
}

function parse<T extends TSchema>(schema: T, bytes: string) {
	const value: unknown = JSON.parse(bytes);
	if (!Check(schema, value)) throw Error("Invalid duty record; check the shift, stop or progress schema");
	return value;
}

export function loadShift(file: string): Shift {
	return parseShift(readFileSync(file, "utf8"));
}

export function parseShift(contents: string): Shift {
	const card = parse(shift, contents);
	if (!(Date.parse(card.start) < Date.parse(card.end))) throw Error("Invalid shift interval");
	const keys = new Set<string>();
	for (const target of card.targets) {
		if (!isAbsolute(target.project) || keys.has(target.key))
			throw Error("Require absolute project and unique target key");
		keys.add(target.key);
		const names = new Set(target.rules.map((r) => r.name));
		if (
			names.size !== target.rules.length ||
			target.rules.some((r) => r.requires && !target.rules.some((p) => p.exception && p.name === r.requires))
		)
			throw Error(`Duplicate or unresolved rule in ${target.key}`);
	}
	return card;
}

function evidenceDigest(root: string, file: string) {
	const path = realpathSync(resolve(root, file));
	const local = relative(realpathSync(root), path);
	if (isAbsolute(file) || !local || local === ".." || local.startsWith(`..${sep}`) || isAbsolute(local))
		throw Error("Evidence outside target key");
	const stat = statSync(path);
	if (!stat.isFile()) throw Error(`Invalid evidence file: ${file}`);
	const fd = openSync(path, "r");
	try {
		const hash = createHash("sha256");
		const buffer = Buffer.allocUnsafe(64 * 1024);
		for (let length = readSync(fd, buffer); length > 0; length = readSync(fd, buffer))
			hash.update(buffer.subarray(0, length));
		return hash.digest("hex");
	} finally {
		closeSync(fd);
	}
}

function verifyProof(root: string, ref: Static<typeof proof>) {
	if (evidenceDigest(root, ref.path) !== ref.sha256) throw Error(`Evidence changed: ${ref.path}`);
}

export function publishDutyFact(
	card: Shift,
	target: Card,
	fact: {
		id: string;
		state: "ready" | "waiting" | "done" | "stopped" | "result";
		action: string;
		minutes: number;
		reason: string;
		path: string;
		gate: "clear" | "blocked";
	},
) {
	const root = join(target.project, ".agenticdoc", target.key);
	const directory = join(root, "duty", card.shift);
	const evidence = { path: fact.path, sha256: evidenceDigest(root, fact.path) };
	const data =
		fact.state === "result"
			? parse(
					result,
					JSON.stringify({
						id: fact.id,
						session: target.session,
						binding: target.binding,
						evidence,
						usedMinutes: fact.minutes,
					}),
				)
			: parse(
					snapshot,
					JSON.stringify({
						...fact,
						shift: card.shift,
						claim: target.claim,
						binding: target.binding,
						session: target.session,
						evidence,
					}),
				);
	const file =
		fact.state === "result" ? join(directory, "results", `${fact.id}.json`) : join(directory, "current.json");
	mkdirSync(dirname(file), { recursive: true });
	const body = JSON.stringify(data);
	if (existsSync(file) && readFileSync(file, "utf8") === body) return file;
	const tmp = `${file}.${randomUUID()}.tmp`;
	writeFileSync(tmp, body, { flag: "wx" });
	if (fact.state === "result") {
		try {
			linkSync(tmp, file);
		} finally {
			unlinkSync(tmp);
		}
	} else renameSync(tmp, file);
	return file;
}

/** Synchronous single-writer outbox. The window holds the per-target OS lease for its lifetime. */
export class WindowDuty {
	readonly watch: StopWatch;
	readonly directory: string;
	readonly input: string;
	readonly target: Card;
	readonly shift: Shift;
	private file: string;
	private ledger: Ledger;
	private notices = new Map<string, string>();
	private idleSince?: number;

	constructor(shiftCard: Shift, target: Card, home?: string) {
		this.shift = shiftCard;
		this.target = target;
		this.watch = new StopWatch(target.project, target.key, target.claim, target.binding, home);
		this.directory = join(target.project, ".agenticdoc", target.key, "duty", shiftCard.shift);
		this.input = join(this.directory, "current.json");
		this.file = join(this.watch.channel.dir, target.key, "duty-ledger", `${shiftCard.shift}.json`);
		const card = digest(JSON.stringify([shiftCard.start, shiftCard.end, target]));
		this.ledger = existsSync(this.file) ? JSON.parse(readFileSync(this.file, "utf8")) : { card, entries: [] };
		if (card !== this.ledger.card)
			throw Error("Shift card changed. Reconcile outstanding reservations before a new shift.");
	}
	get entries(): ReadonlyArray<Readonly<Entry>> {
		return this.ledger.entries;
	}
	get balance() {
		return this.target.minutes - this.entries.reduce((sum, e) => sum + e.charged, 0);
	}

	private save() {
		mkdirSync(dirname(this.file), { recursive: true });
		const tmp = `${this.file}.${randomUUID()}.tmp`;
		try {
			writeFileSync(tmp, JSON.stringify(this.ledger), { flag: "wx", mode: 0o600 });
			renameSync(tmp, this.file);
		} catch (error) {
			this.ledger = existsSync(this.file)
				? JSON.parse(readFileSync(this.file, "utf8"))
				: { card: this.ledger.card, entries: [] };
			if (existsSync(tmp)) unlinkSync(tmp);
			throw error;
		}
	}

	private notify(kind: Notice["kind"], id: string, summary: string, emit: (n: Notice) => void) {
		const fingerprint = JSON.stringify([kind, summary]);
		if (this.notices.get(id) === fingerprint) return;
		emit({ kind, key: this.target.key, id, summary });
		this.notices.set(id, fingerprint);
	}

	private settle(entry: Entry) {
		const file = join(this.directory, "results", `${entry.id}.json`);
		if (!existsSync(file)) return;
		const actual = parse(result, readFileSync(file, "utf8"));
		if (
			actual.id !== entry.id ||
			actual.binding !== this.target.binding ||
			actual.session !== this.target.session ||
			(!entry.inherited && actual.usedMinutes > entry.charged) ||
			actual.evidence.sha256 === entry.evidence
		)
			throw Error("Invalid progress or settlement");
		verifyProof(dirname(dirname(this.directory)), actual.evidence);
		entry.stage = "complete";
		entry.charged = entry.inherited ? 0 : actual.usedMinutes;
		entry.progress = actual.evidence.path;
		this.save();
	}

	private reserve(entry: Entry, action: Static<typeof rule>, now: number) {
		entry.message = [
			`MW duty ${this.shift.shift} / ${entry.id}`,
			action.direction,
			`Scope: ${action.scope}`,
			`Reserved minutes including review: ${entry.minutes}`,
			`Shift ends: ${this.shift.end}`,
			"Obey the original gates, stop and report actual progress under duty/" +
				this.shift.shift +
				"/results/" +
				entry.id +
				".json.",
		].join("\n");
		entry.charged = entry.minutes;
		entry.at = now;
		entry.stage = "reserved";
		this.save();
	}

	poll(now: number, emit: (notice: Notice) => void, decision?: { id: string; approve: boolean; reason: string }) {
		const { key, binding, claim, session } = this.target;
		const sample = this.watch.sample();
		const live = this.watch.channel.status(key);
		const active = now >= Date.parse(this.shift.start) && now < Date.parse(this.shift.end);
		const halted = existsSync(join(this.directory, "STOP"));
		const source = existsSync(this.input) ? readFileSync(this.input) : undefined;
		const hash = source ? digest(source) : "missing";

		// Reconcile deliveries before deciding whether a newly observed stop needs a turn.
		for (const entry of this.ledger.entries) {
			if (!entry.message || entry.stage === "complete") continue;
			const request = this.watch.channel.messagePath(key, binding, entry.id, "request");
			if (!existsSync(request)) continue;
			const receipt: Record<string, unknown> = this.watch.channel.receipt(key, binding, entry.id);
			const state = String(receipt.state);
			if (
				receipt.id !== entry.id ||
				receipt.binding !== binding ||
				receipt.key !== key ||
				(receipt.session !== undefined && receipt.session !== session) ||
				(receipt.claim !== undefined && receipt.claim !== claim)
			)
				throw Error("Receipt identity mismatch");
			if (entry.receipt !== state) {
				entry.receipt = state;
				if (entry.stage === "reserved") entry.stage = "tracking";
				this.save();
			}
			if (state === "started" && entry.approved === false && entry.stage !== "denied") {
				entry.stage = "denied";
				this.save();
			} else if (state === "started" && entry.approved !== false) this.settle(entry);
			else if (
				!["queued", "received", "started"].includes(state) &&
				entry.stage !== "denied" &&
				entry.stage !== "diagnosis"
			) {
				entry.stage = "diagnosis";
				this.save();
			}
		}

		if (!active || halted || sample.state === "finished") {
			if (source && !this.entries.some((e) => e.hash === hash && e.stage === "complete"))
				this.notify(
					"user",
					hash,
					`Handoff: shift inactive, stopped or key finished. Pending evidence: ${this.input}`,
					emit,
				);
			return;
		}
		if (
			!live.connected ||
			live.session !== session ||
			live.claim !== claim ||
			live.binding !== binding ||
			["offline", "binding-changed", "unobservable"].includes(sample.state)
		) {
			this.idleSince = undefined;
			this.notify(
				"duty",
				`${key}-identity`,
				`Delivery suspended. Reconcile original binding and queue for ${key}`,
				emit,
			);
			return;
		}
		this.notices.delete(`${key}-identity`);
		if (sample.state === "working" || sample.state === "waiting-for-worker") {
			this.idleSince = undefined;
			return;
		}
		this.idleSince ??= now;
		if (now - this.idleSince < 45_000) return;

		if (!source) {
			const existing = this.entries.find((e) => e.hash === "missing");
			const id = existing?.id ?? randomUUID();
			if (!existing) {
				this.ledger.entries.push({
					id,
					fingerprint: "missing",
					hash,
					action: "report-stop",
					reason: "Missing structured stop",
					evidence: "",
					minutes: 0,
					charged: 0,
					at: now,
					stage: "reserved",
					message:
						"Report the current stop using mw_duty_report (or the current.json protocol) at " +
						this.input +
						". Allowed action names: " +
						this.target.rules.map((r) => r.name).join(", ") +
						". No new work authorized.",
				});
				this.save();
			}
			const record = this.ledger.entries.find((e) => e.id === id)!;
			this.deliver(record, now);
			if (record.receipt && now - record.at >= 15 * 60000)
				this.notify("duty", id, `No structured stop after request ${id}`, emit);
			return;
		}
		const stop = parse(snapshot, source.toString("utf8"));
		if (decision && stop.id !== decision.id) throw Error("Decision refers to a superseded stop");
		if (
			stop.shift !== this.shift.shift ||
			stop.claim !== claim ||
			stop.session !== session ||
			stop.binding !== binding
		)
			throw Error("Stop does not belong to pinned window and shift");
		if (stop.state !== "ready") return;
		const fingerprint = digest(JSON.stringify([stop.action, stop.evidence, stop.minutes, stop.gate]));
		let entry = this.ledger.entries.find((e) => e.id === stop.id || e.fingerprint === fingerprint);
		if (entry && entry.id === stop.id && entry.hash !== hash) throw Error("Stop ID reused with changed facts");
		if (entry && entry.id !== stop.id) return;
		if (!entry) {
			entry = {
				id: stop.id,
				fingerprint,
				hash,
				action: stop.action,
				reason: stop.reason,
				evidence: stop.evidence.sha256,
				minutes: stop.minutes,
				charged: 0,
				at: now,
				stage: "decision",
			};
			const request = this.watch.channel.messagePath(key, binding, stop.id, "request");
			if (existsSync(request)) {
				const previous = JSON.parse(readFileSync(request, "utf8"));
				if (
					previous.key !== key ||
					previous.claim !== claim ||
					previous.binding !== binding ||
					previous.id !== stop.id ||
					typeof previous.text !== "string"
				)
					throw Error("Prior direction identity mismatch");
				// Prior shift owns the reservation. Follow its receipt without granting the exception or spending again.
				entry.message = previous.text;
				entry.stage = "tracking";
				entry.inherited = true;
			}
			this.ledger.entries.push(entry);
			this.save();
		}
		if (entry.stage === "complete" || entry.stage === "denied") return;
		if (entry.stage === "tracking" && now - (entry.sentAt ?? entry.at) >= entry.minutes * 60000 + 45_000) {
			entry.stage = "diagnosis";
			this.save();
		}
		if (entry.stage === "diagnosis") {
			this.notify(
				"duty",
				entry.id,
				`Receipt ${entry.receipt}, no verified progress for ${entry.id}. Inspect ${stop.evidence.path}`,
				emit,
			);
			return;
		}
		if (entry.stage === "tracking") return;
		verifyProof(dirname(dirname(this.directory)), stop.evidence);
		const action = this.target.rules.find((r) => r.name === stop.action);
		const previous = this.entries.filter((e) => e.id !== stop.id);
		const unavailable =
			!action ||
			stop.gate !== "clear" ||
			stop.minutes < 1 ||
			stop.minutes > action.limit ||
			stop.minutes > this.balance + entry.charged ||
			now + stop.minutes * 60000 > Date.parse(this.shift.end) ||
			(action.requires &&
				!previous.some((e) => e.action === action.requires && e.approved && e.receipt === "started")) ||
			((action.exception || action.once) &&
				previous.some((e) => e.action === action.name && (e.message || e.stage === "denied")));
		if (unavailable || !action) {
			if (entry.stage !== "handoff") {
				entry.stage = "handoff";
				this.save();
			}
			this.notify(
				"user",
				stop.id,
				`Held for scope, gate, remaining budget or prior authorization: ${stop.reason}`,
				emit,
			);
			return;
		}
		if (!entry.message && action.exception) {
			if (!decision || decision.id !== stop.id) {
				if (entry.lastWake !== undefined && now - entry.lastWake < 15 * 60_000) return;
				if ((entry.wakeCount ?? 0) >= 2) {
					this.notify("user", stop.id, `Unresolved delegated decision after reminder: ${stop.reason}`, emit);
					return;
				}
				const summary = {
					shift: this.shift.shift,
					key,
					claim,
					binding,
					session,
					id: stop.id,
					reason: stop.reason,
					action: action.direction,
					scope: action.scope,
					minutes: stop.minutes,
					available: this.balance,
					end: this.shift.end,
					evidence: stop.evidence,
					workers: sample.state,
					priorReceipt: entry.receipt ?? null,
				};
				emit({ kind: "duty", id: stop.id, key, summary: JSON.stringify(summary) });
				entry.lastWake = now;
				entry.wakeCount = (entry.wakeCount ?? 0) + 1;
				this.save();
				return;
			}
			entry.approved = decision.approve;
			entry.decision = decision.reason;
			if (!decision.approve) {
				entry.message = `MW duty ${this.shift.shift} declines ${action.name}. No new work authorized. ${decision.reason}`;
				entry.stage = "reserved";
				this.save();
				this.deliver(entry, now);
				return;
			}
		}
		if (!entry.message) this.reserve(entry, action, now);
		this.deliver(entry, now);
	}

	private deliver(entry: Entry, now: number) {
		if (!entry.message || entry.receipt) return;
		const { key, binding } = this.target;
		const receipt = this.watch.channel.send(key, binding, entry.id, entry.message, {
			shift: this.shift.shift,
			until: Date.parse(this.shift.end),
			stopHash: entry.hash,
		});
		entry.sentAt = now;
		entry.stage = "tracking";
		entry.receipt = String(receipt.state);
		this.save();
	}
}
