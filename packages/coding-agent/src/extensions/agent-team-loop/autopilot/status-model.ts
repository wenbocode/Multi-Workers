/**
 * status-model.ts — the /autopilot console's stateless view model
 * (goal-autopilot T-15, design D-005/D-109/D-110, AC-015/AC-018).
 *
 * Everything here is DERIVED FROM FILES on every call — the console keeps no
 * process state (D-005: 断点重开 = 正常重开). One derivation feeds both the
 * human-readable view and `--json` (view parity, VC-017).
 *
 * File-family schemas are owned by the Python side; this module mirrors the
 * read-side rules it needs:
 *   - _roadmap.md                      → autopilot/roadmap.py (D-105 section
 *     schema; lenient view-side parse — malformed pieces become warnings,
 *     while the conductor is the one that hard-fails and skips its tick)
 *   - gates/gate-{seq:04d}.md          → autopilot/gates.py (12-field
 *     frontmatter YAML subset, status enum, seq-ordered directory scan)
 *   - timeline.jsonl + .1/.2 rotations → autopilot/timeline.py (query_events
 *     watermark / ev_filter / pruned semantics, D-109)
 *   - _autopilot/config.json           → autopilot/config.py (13 fields,
 *     D-110; present-but-invalid fails closed, missing file = defaults)
 *   - rounds derivation                → autopilot/state.py used_rounds
 *     (distinct attempt per loop label; a missing attempt label degrades to
 *     directory-identity counting — VC-020 locks both implementations to
 *     the same result over the same task dirs)
 *   - key phase                        → _index.parallel via shared/index-store.ts
 *
 * Loop families per key (design §4.1 round table): `l2:{key}:{edge}` → l2,
 * `l3:{key}` → l3, `exec:{key}:{stem}` and `repair:{key}` → retry. A
 * family's `used` is its most-consumed loop — budgets are enforced per loop
 * (AC-008/AC-011), so the maximum is the binding constraint; a key that
 * spent one round on each of several edges is NOT exhausted. `max` is
 * config round_budget for all three families (single source, AC-011).
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { IndexStore } from "../shared/index-store.ts";

// ── Autopilot file-family paths (explicit, derived from projectDir) ─────────

export function autopilotDir(projectDir: string): string {
	return path.join(projectDir, ".agenticdoc", "_autopilot");
}

export function roadmapPath(projectDir: string): string {
	return path.join(autopilotDir(projectDir), "_roadmap.md");
}

export function gatesDir(projectDir: string): string {
	return path.join(autopilotDir(projectDir), "gates");
}

export function timelinePath(projectDir: string): string {
	return path.join(autopilotDir(projectDir), "timeline.jsonl");
}

export function configPath(projectDir: string): string {
	return path.join(autopilotDir(projectDir), "config.json");
}

/** `.mw/gates.lock` — the O_CREAT|O_EXCL gate answer lock (D-105). */
export function gatesLockPath(projectDir: string): string {
	return path.join(projectDir, ".mw", "gates.lock");
}

/** `.mw/autopilot-config.lock` — the O_CREAT|O_EXCL lock guarding the
 * config.json read-modify-write (mw-autopilot-verify-cli D-006). Same path
 * family and protocol as the other `.mw/` locks; the Python writer takes the
 * byte-identical path (plan §2.2), so the two sides are mutually exclusive. */
export function configLockPath(projectDir: string): string {
	return path.join(projectDir, ".mw", "autopilot-config.lock");
}

// ── config.json (mirror of autopilot/config.py, D-110) ──────────────────────

export interface AutopilotConfig {
	enabled: boolean;
	paused: boolean;
	poll_interval_sec: number;
	max_parallel_keys: number;
	round_budget: number;
	worker_timeout_min: number;
	l2_read_file_cap: number;
	l2_read_byte_cap: number;
	/** Consecutive same-edge advance failures before the key is marked
	 * stalled (mw-autopilot-stall-feedback AC-003). Optional in the file —
	 * absent falls back to the default. */
	advance_stall_ticks: number;
	/** Cross-key red repair channel (xkey-repair-mechanism AC-008). Off by
	 * default so every existing flow is untouched until a project opts in. */
	xkey_repair: boolean;
	/** Per-project verification argv — no shell, so a list is the contract
	 * (D-007). */
	xkey_verify_cmd: string[];
	/** Conductor verification-subprocess timeout in seconds (>= 1). */
	xkey_verify_timeout_s: number;
	/** Workspace-root selector for xkey verification (conductor-resolved).
	 * "" = auto (workspace_root). The schema only requires a string; the
	 * root-name validity is resolved at parse time (plan §2.2). */
	xkey_verify_cwd: string;
}

export const DEFAULT_CONFIG: AutopilotConfig = {
	enabled: false,
	paused: false,
	poll_interval_sec: 4,
	max_parallel_keys: 2,
	round_budget: 2,
	worker_timeout_min: 30,
	l2_read_file_cap: 8,
	l2_read_byte_cap: 65536,
	advance_stall_ticks: 5,
	xkey_repair: false,
	xkey_verify_cmd: [],
	xkey_verify_timeout_s: 1800,
	xkey_verify_cwd: "",
};

/** Fresh copy of the defaults that callers may mutate freely — mirror of
 * config.py default_config(). `xkey_verify_cmd` is an array, so a shallow
 * spread would hand every reader the same mutable DEFAULT_CONFIG element. */
function freshDefaults(): AutopilotConfig {
	return { ...DEFAULT_CONFIG, xkey_verify_cmd: [...DEFAULT_CONFIG.xkey_verify_cmd] };
}

export const BOOL_FIELDS = ["enabled", "paused", "xkey_repair"] as const;

/** field → list of non-empty strings — identical to config.py _LIST_FIELDS. */
export const LIST_FIELDS = ["xkey_verify_cmd"] as const;

/** Plain string fields — identical to config.py _STRING_FIELDS. */
export const STR_FIELDS = ["xkey_verify_cwd"] as const;

/** field → [min, max|null] — identical to config.py _INT_RANGES. */
export const INT_RANGES: Record<string, [number, number | null]> = {
	poll_interval_sec: [1, 5],
	max_parallel_keys: [2, null],
	round_budget: [1, null],
	worker_timeout_min: [1, null],
	l2_read_file_cap: [1, null],
	l2_read_byte_cap: [1, null],
	advance_stall_ticks: [1, 50],
	xkey_verify_timeout_s: [1, null],
};

/** Node >= 22 hands the reviver a third argument whose `context.source` is the
 * ORIGINAL literal text for primitive values. That is the only way to tell
 * `4.0` / `4.00` / `1e2` / `-0.0` apart from `4` — JSON.parse normalizes all of
 * them to the integer number 4 (design D-007 Direction B). The lib.es5
 * `JSON.parse` overload has no such parameter, so the reviver is narrowed here
 * and cast once at the call site (no `any`). */
type ConfigReviverContext = { source?: string };

/** Pure JSON integer literal — exactly the forms Python's `int` accepts from
 * `json.loads`, so the two schema owners agree on every literal. */
const INT_LITERAL_RE = /^-?(?:0|[1-9]\d*)$/;

/** Raised by configReviver so readConfig can report the field and literal
 * instead of a generic parse error. */
class IntegerLiteralError extends Error {
	constructor(field: string, literal: string) {
		super(`invalid _autopilot/config.json: ${field}: expected an integer literal, got ${literal}`);
		this.name = "IntegerLiteralError";
	}
}

/** JSON.parse reviver rejecting non-integer literals for the int fields. */
function configReviver(this: unknown, key: string, value: unknown, context?: ConfigReviverContext): unknown {
	if (typeof value !== "number" || !Number.isInteger(value)) return value;
	if (!Object.hasOwn(INT_RANGES, key)) return value;
	const source = context?.source;
	if (source !== undefined && !INT_LITERAL_RE.test(source)) throw new IntegerLiteralError(key, source);
	return value;
}

/** Validate a raw config object exactly like config.py validate_config:
 * unknown fields and out-of-range values fail closed, naming every offender.
 * Bool fields are checked before the int rules (JSON booleans would
 * otherwise pass number checks). Absent fields are fine — they fall back to
 * their defaults at read time. */
export function validateConfigData(data: unknown): string[] {
	if (typeof data !== "object" || data === null || Array.isArray(data)) {
		return ["config root must be a JSON object"];
	}
	const cfg = data as Record<string, unknown>;
	const errors: string[] = [];
	const known = new Set<string>(Object.keys(DEFAULT_CONFIG));
	const unknown = Object.keys(cfg)
		.filter((k) => !known.has(k))
		.sort();
	if (unknown.length > 0) errors.push(`unknown field(s): ${unknown.join(", ")}`);
	for (const field of BOOL_FIELDS) {
		if (field in cfg && typeof cfg[field] !== "boolean") {
			errors.push(`${field}: expected true/false, got ${JSON.stringify(cfg[field])}`);
		}
	}
	for (const field of LIST_FIELDS) {
		if (!(field in cfg)) continue;
		const value = cfg[field];
		if (!Array.isArray(value) || !value.every((item) => typeof item === "string" && item !== "")) {
			errors.push(`${field}: expected a list of non-empty strings, got ${JSON.stringify(value)}`);
		}
	}
	for (const field of STR_FIELDS) {
		if (field in cfg && typeof cfg[field] !== "string") {
			errors.push(`${field}: expected string, got ${JSON.stringify(cfg[field])}`);
		}
	}
	for (const [field, [lo, hi]] of Object.entries(INT_RANGES)) {
		if (!(field in cfg)) continue;
		const value = cfg[field];
		if (typeof value !== "number" || !Number.isInteger(value)) {
			errors.push(`${field}: expected integer, got ${JSON.stringify(value)}`);
			continue;
		}
		if (value < lo) errors.push(`${field}: must be >= ${lo}, got ${value}`);
		if (hi !== null && value > hi) errors.push(`${field}: must be <= ${hi}, got ${value}`);
	}
	return errors;
}

export type ConfigResult = { ok: true; config: AutopilotConfig } | { ok: false; error: string };

/** Read _autopilot/config.json. A missing file is NOT an error — it means
 * "autopilot never enabled" and yields the defaults with zero footprint
 * (D-110). A present-but-invalid file fails closed with every offending
 * field named (config.py load_config semantics). Fields absent from a
 * partial file fall back to their defaults (view-side robustness; saves
 * normalize the file to the full canonical set). */
export function readConfig(projectDir: string): ConfigResult {
	const file = configPath(projectDir);
	let raw: string;
	try {
		raw = fs.readFileSync(file, "utf8");
	} catch (err) {
		if ((err as NodeJS.ErrnoException).code === "ENOENT") return { ok: true, config: freshDefaults() };
		return { ok: false, error: `cannot read ${file}: ${String(err)}` };
	}
	let data: unknown;
	try {
		data = JSON.parse(raw, configReviver as (this: unknown, key: string, value: unknown) => unknown);
	} catch (err) {
		if (err instanceof IntegerLiteralError) return { ok: false, error: err.message };
		return { ok: false, error: `cannot parse ${file}: ${String(err)}` };
	}
	const errors = validateConfigData(data);
	if (errors.length > 0) return { ok: false, error: `invalid _autopilot/config.json: ${errors.join("; ")}` };
	// Post-validation every present field has the right type; absent fields
	// keep their defaults.
	const cfg = data as Record<string, unknown>;
	const boolOf = (name: "enabled" | "paused" | "xkey_repair"): boolean =>
		typeof cfg[name] === "boolean" ? (cfg[name] as boolean) : DEFAULT_CONFIG[name];
	const intOf = (
		name:
			| "poll_interval_sec"
			| "max_parallel_keys"
			| "round_budget"
			| "worker_timeout_min"
			| "l2_read_file_cap"
			| "l2_read_byte_cap"
			| "advance_stall_ticks"
			| "xkey_verify_timeout_s",
	): number => (typeof cfg[name] === "number" ? (cfg[name] as number) : DEFAULT_CONFIG[name]);
	const listOf = (name: "xkey_verify_cmd"): string[] =>
		Array.isArray(cfg[name]) ? (cfg[name] as string[]) : [...DEFAULT_CONFIG[name]];
	const strOf = (name: "xkey_verify_cwd"): string =>
		typeof cfg[name] === "string" ? cfg[name] : DEFAULT_CONFIG[name];
	const merged: AutopilotConfig = {
		enabled: boolOf("enabled"),
		paused: boolOf("paused"),
		poll_interval_sec: intOf("poll_interval_sec"),
		max_parallel_keys: intOf("max_parallel_keys"),
		round_budget: intOf("round_budget"),
		worker_timeout_min: intOf("worker_timeout_min"),
		l2_read_file_cap: intOf("l2_read_file_cap"),
		l2_read_byte_cap: intOf("l2_read_byte_cap"),
		advance_stall_ticks: intOf("advance_stall_ticks"),
		xkey_repair: boolOf("xkey_repair"),
		xkey_verify_cmd: listOf("xkey_verify_cmd"),
		xkey_verify_timeout_s: intOf("xkey_verify_timeout_s"),
		xkey_verify_cwd: strOf("xkey_verify_cwd"),
	};
	return { ok: true, config: merged };
}

/** Validate, then atomically write config.json (tmp + rename, UTF-8, LF,
 * indent-2 + trailing newline — the exact shape config.py save_config
 * writes and parses back). The write always normalizes to the full
 * canonical field set in DEFAULT_CONFIG order. */
export function saveConfig(projectDir: string, config: AutopilotConfig): { ok: true } | { ok: false; error: string } {
	const errors = validateConfigData(config);
	if (errors.length > 0) return { ok: false, error: `invalid _autopilot/config.json: ${errors.join("; ")}` };
	const ordered: AutopilotConfig = {
		enabled: config.enabled,
		paused: config.paused,
		poll_interval_sec: config.poll_interval_sec,
		max_parallel_keys: config.max_parallel_keys,
		round_budget: config.round_budget,
		worker_timeout_min: config.worker_timeout_min,
		l2_read_file_cap: config.l2_read_file_cap,
		l2_read_byte_cap: config.l2_read_byte_cap,
		advance_stall_ticks: config.advance_stall_ticks,
		xkey_repair: config.xkey_repair,
		xkey_verify_cmd: [...config.xkey_verify_cmd],
		xkey_verify_timeout_s: config.xkey_verify_timeout_s,
		xkey_verify_cwd: config.xkey_verify_cwd,
	};
	const file = configPath(projectDir);
	try {
		fs.mkdirSync(path.dirname(file), { recursive: true });
		const tmp = `${file}.tmp`;
		fs.writeFileSync(tmp, `${JSON.stringify(ordered, null, 2)}\n`, "utf8");
		fs.renameSync(tmp, file);
	} catch (err) {
		return { ok: false, error: `cannot write ${file}: ${String(err)}` };
	}
	return { ok: true };
}

// ── _roadmap.md (lenient view-side parse of the D-105 schema) ────────────────

export const STAGE_STATUSES = ["pending", "approved", "running", "closed", "closed-human", "halted"] as const;
export const KEY_STATUSES = ["running", "done", "stalled", "closed-legacy"] as const;

export interface RoadmapKey {
	key: string;
	role: string;
	dependsOn: string[];
}

export interface RoadmapStage {
	number: number;
	title: string;
	goal: string;
	status: string;
	/** key → running|done|stalled|closed-legacy (D-105 KEY_STATUSES).
	 * Values are kept verbatim; ones outside the enum surface as parse
	 * warnings instead of being dropped. */
	keyStatus: Record<string, string>;
	keys: RoadmapKey[];
}

export interface RoadmapParse {
	stages: RoadmapStage[];
	warnings: string[];
}

const STAGE_PREFIX_RE = /^##\s*Stage\b/;
const STAGE_HEADER_RE = /^##\s*Stage\s+(\d+)\s*:\s*(.+)$/;
const ROADMAP_FIELD_RE = /^>\s*([A-Za-z][A-Za-z0-9_-]*)\s*:\s*(.*)$/;
const SEPARATOR_CELL_RE = /^:?-+:?$/;

function splitTableRow(line: string): string[] {
	let body = line.startsWith("|") ? line.slice(1) : line;
	if (body.endsWith("|")) body = body.slice(0, -1);
	return body.split("|").map((c) => c.trim());
}

function isKeysHeaderRow(cells: string[]): boolean {
	return (
		cells.length === 3 &&
		cells[0].toLowerCase() === "key" &&
		cells[1].toLowerCase() === "role" &&
		cells[2].toLowerCase() === "depends_on"
	);
}

function parseDependsOn(cell: string): string[] {
	const trimmed = cell.trim();
	if (trimmed === "" || trimmed === "-") return [];
	const deps: string[] = [];
	for (const part of trimmed.split(",")) {
		const p = part.trim();
		if (p !== "" && p !== "-") deps.push(p);
	}
	return deps;
}

/** Parse roadmap markdown into stages + warnings. Never throws — this is the
 * view side of roadmap.py's strict parser: structural problems the conductor
 * treats as skip-the-tick errors degrade here to warnings plus whatever
 * stages did parse, so the console always has something honest to show. */
export function parseRoadmapText(text: string): RoadmapParse {
	const warnings: string[] = [];
	const stages: RoadmapStage[] = [];
	let cur: { stage: RoadmapStage; seenKeys: Set<string>; seenFields: Set<string> } | null = null;
	let inKeysTable = false;
	let tableHeaderSeen = false;

	const finish = (): void => {
		if (cur === null) return;
		if (!cur.seenFields.has("status")) {
			warnings.push(`stage ${cur.stage.number}: missing '> status:' line (shown as pending)`);
			cur.stage.status = "pending";
		}
		if (!cur.seenFields.has("goal")) {
			warnings.push(`stage ${cur.stage.number}: missing '> goal:' line`);
		}
		stages.push(cur.stage);
		cur = null;
	};

	const lines = text.split(/\r\n|\r|\n/);
	for (let lineno = 1; lineno <= lines.length; lineno++) {
		const line = lines[lineno - 1].trim();
		if (line === "") continue;
		if (line.startsWith("#")) {
			if (line.startsWith("###")) {
				const heading = line.replace(/^#+/, "").trim();
				if (cur !== null && heading.toLowerCase() === "keys") {
					inKeysTable = true;
					tableHeaderSeen = false;
				} else {
					inKeysTable = false; // any other subsection ends the keys table
				}
				continue;
			}
			if (line.startsWith("##")) {
				if (STAGE_PREFIX_RE.test(line)) {
					const m = STAGE_HEADER_RE.exec(line);
					if (m === null) {
						warnings.push(`line ${lineno}: malformed stage header (expected '## Stage <number>: <title>')`);
						finish();
						inKeysTable = false;
						continue;
					}
					finish();
					cur = {
						stage: {
							number: Number(m[1]),
							title: (m[2] ?? "").trim(),
							goal: "",
							status: "pending",
							keyStatus: {},
							keys: [],
						},
						seenKeys: new Set(),
						seenFields: new Set(),
					};
				} else {
					finish(); // an unrelated H2 section ends the current stage
				}
				inKeysTable = false;
				continue;
			}
			// H1 title or deeper heading — ignored.
			inKeysTable = false;
			continue;
		}
		if (line.startsWith("|")) {
			if (cur !== null && inKeysTable) {
				const cells = splitTableRow(line);
				if (cells.length > 0 && cells.every((c) => SEPARATOR_CELL_RE.test(c))) continue; // |----| separator row
				if (!tableHeaderSeen && isKeysHeaderRow(cells)) {
					tableHeaderSeen = true;
					continue;
				}
				if (cells.length !== 3) {
					warnings.push(
						`line ${lineno} (stage ${cur.stage.number}): keys table row must have 3 columns (key | role | depends_on), got ${cells.length}`,
					);
					continue;
				}
				const key = cells[0] ?? "";
				if (key === "") {
					warnings.push(`line ${lineno} (stage ${cur.stage.number}): keys table row has empty key cell`);
					continue;
				}
				if (cur.seenKeys.has(key)) {
					warnings.push(`line ${lineno} (stage ${cur.stage.number}): duplicate key row '${key}'`);
					continue;
				}
				cur.seenKeys.add(key);
				cur.stage.keys.push({ key, role: cells[1] ?? "", dependsOn: parseDependsOn(cells[2] ?? "") });
			}
			// Pipe rows outside a keys table (prose tables) are ignored.
			continue;
		}
		if (line.startsWith(">")) {
			const m = ROADMAP_FIELD_RE.exec(line);
			const name = m?.[1] ?? "";
			const value = (m?.[2] ?? "").trim();
			if (cur !== null) {
				if (name === "goal" || name === "status" || name === "key-status") {
					if (cur.seenFields.has(name)) {
						warnings.push(
							`line ${lineno} (stage ${cur.stage.number}): duplicate '> ${name}:' line (last one wins)`,
						);
					} else {
						cur.seenFields.add(name);
					}
					if (name === "goal") cur.stage.goal = value;
					else if (name === "status") {
						if (!(STAGE_STATUSES as readonly string[]).includes(value)) {
							warnings.push(`line ${lineno} (stage ${cur.stage.number}): invalid status '${value}'`);
						}
						cur.stage.status = value;
					} else {
						parseKeyStatusLine(value, cur.stage, lineno, warnings);
					}
				}
				// Other blockquote lines (prose, header fields) are ignored.
				inKeysTable = false;
			}
			continue;
		}
		// Any other line (prose) is ignored but ends the keys table.
		inKeysTable = false;
	}
	finish();
	if (stages.length === 0) warnings.push("no '## Stage <number>: <title>' sections found");
	return { stages, warnings };
}

function parseKeyStatusLine(value: string, stage: RoadmapStage, lineno: number, warnings: string[]): void {
	for (const part of value.split(",")) {
		const entry = part.trim();
		if (entry === "") continue;
		const eq = entry.indexOf("=");
		if (eq <= 0) {
			warnings.push(
				`line ${lineno} (stage ${stage.number}): malformed key-status entry '${entry}' (expected <key>=<status>)`,
			);
			continue;
		}
		const key = entry.slice(0, eq).trim();
		const status = entry.slice(eq + 1).trim();
		if (key === "") {
			warnings.push(
				`line ${lineno} (stage ${stage.number}): malformed key-status entry '${entry}' (expected <key>=<status>)`,
			);
			continue;
		}
		if (!(KEY_STATUSES as readonly string[]).includes(status)) {
			warnings.push(`line ${lineno} (stage ${stage.number}): key '${key}' has invalid status '${status}'`);
		}
		if (key in stage.keyStatus) {
			warnings.push(
				`line ${lineno} (stage ${stage.number}): duplicate key-status entry for '${key}' (last one wins)`,
			);
		}
		stage.keyStatus[key] = status;
	}
}

export type RoadmapResult = { ok: true; stages: RoadmapStage[]; warnings: string[] } | { ok: false; error: string };

export function readRoadmap(projectDir: string): RoadmapResult {
	const file = roadmapPath(projectDir);
	let text: string;
	try {
		text = fs.readFileSync(file, "utf8");
	} catch {
		return { ok: false, error: `roadmap file not found: ${file}` };
	}
	const parse = parseRoadmapText(text);
	return { ok: true, stages: parse.stages, warnings: parse.warnings };
}

// ── gates (view-side enumeration, mirror of autopilot/gates.py) ──────────────

export const GATE_KINDS = [
	"stage-confirm",
	"stage-close",
	"stalled",
	"budget-exhausted",
	"goal-change",
	"xkey-authorize",
] as const;
export const GATE_STATUSES = ["pending", "approved", "rejected"] as const;

/** Canonical frontmatter field order (gates.py FRONTMATTER_FIELDS). */
export const GATE_FRONTMATTER_FIELDS = [
	"id",
	"kind",
	"stage",
	"key",
	"created_at",
	"created_by",
	"question",
	"context_refs",
	"status",
	"answered_at",
	"answered_by",
	"note",
] as const;

export interface GateRecord {
	id: string;
	kind: string;
	status: string;
	stage: number | null;
	key: string | null;
	question: string;
	createdAt: string;
	path: string;
}

class GateFormatError extends Error {}

const GATE_FILE_RE = /^gate-(\d+)\.md$/;
const GATE_FIELD_LINE_RE = /^([A-Za-z_][A-Za-z0-9_]*):(?:[ \t]+(.*))?[ \t]*$/;
const GATE_LIST_ITEM_RE = /^[ \t]+-[ \t]+(.*)$/;
const GATE_NULL_LITERALS = new Set(["", "~", "-", "null", "Null", "NULL"]);

/** YAML-subset scalar, mirroring gates.py _parse_scalar: single-quoted string
 * ('' escaping), null literal, or plain string. Double-quoted scalars are
 * rejected (no escape-rule support on the Python side either). */
function gateScalar(raw: string | undefined, file: string, lineno: number): string | null {
	if (raw === undefined) return null;
	if (raw.startsWith("'")) {
		if (raw.length < 2 || !raw.endsWith("'")) {
			throw new GateFormatError(`${file}: unterminated single-quoted scalar (line ${lineno}): '${raw}'`);
		}
		return raw.slice(1, -1).replaceAll("''", "'");
	}
	if (raw.startsWith('"')) {
		throw new GateFormatError(`${file}: double-quoted scalars are not supported (line ${lineno}): '${raw}'`);
	}
	if (GATE_NULL_LITERALS.has(raw)) return null;
	return raw;
}

function isIsoTimestamp(value: string): boolean {
	return !Number.isNaN(Date.parse(value));
}

/** Parse one gate file into a GateRecord. Throws GateFormatError on any
 * frontmatter/schema violation — corrupt gate files surface as errors, never
 * as silently wrong queue entries (gates.py parse semantics). */
export function parseGateFile(text: string, file: string): GateRecord {
	const lines = text.split(/\r\n|\r|\n/);
	if (lines.length === 0 || lines[0].trim() !== "---") {
		throw new GateFormatError(`${file}: frontmatter must open with a '---' line`);
	}
	const fields = new Map<string, string | null>();
	const contextRefs: string[] = [];
	const seen = new Set<string>();
	let inRefs = false;
	let closed = false;
	for (let i = 1; i < lines.length; i++) {
		const line = lines[i];
		if (line.trim() === "---") {
			closed = true;
			break;
		}
		if (inRefs) {
			const item = GATE_LIST_ITEM_RE.exec(line);
			if (item !== null) {
				const ref = gateScalar(item[1], file, i + 1);
				if (ref === null || ref === "")
					throw new GateFormatError(`${file}: empty context_refs item (line ${i + 1})`);
				contextRefs.push(ref);
				continue;
			}
			inRefs = false; // dedent: fall through to a normal field line
		}
		const field = GATE_FIELD_LINE_RE.exec(line);
		if (field === null) throw new GateFormatError(`${file}: invalid frontmatter line ${i + 1}: '${line}'`);
		const name = field[1] ?? "";
		if (!(GATE_FRONTMATTER_FIELDS as readonly string[]).includes(name)) {
			throw new GateFormatError(`${file}: unknown frontmatter field '${name}' (line ${i + 1})`);
		}
		if (seen.has(name)) throw new GateFormatError(`${file}: duplicate frontmatter field '${name}' (line ${i + 1})`);
		seen.add(name);
		const raw = field[2];
		if (name === "context_refs") {
			if (raw === undefined || raw === "") {
				fields.set(name, null);
				inRefs = true;
			} else if (raw === "[]") {
				fields.set(name, null);
			} else {
				throw new GateFormatError(`${file}: context_refs must be a block list or [] (line ${i + 1})`);
			}
		} else {
			fields.set(name, gateScalar(raw, file, i + 1));
		}
	}
	if (!closed) throw new GateFormatError(`${file}: frontmatter never closes with a '---' line`);

	const required = (name: string): string => {
		const value = fields.get(name);
		if (typeof value !== "string" || value === "") {
			throw new GateFormatError(`${file}: field '${name}' must be a non-empty string`);
		}
		return value;
	};
	const optional = (name: string): string | null => {
		const value = fields.get(name) ?? null;
		return typeof value === "string" && value !== "" ? value : null;
	};

	const id = required("id");
	if (!/^gate-\d+$/.test(id)) throw new GateFormatError(`${file}: id must match 'gate-<digits>', got '${id}'`);
	const kind = required("kind");
	if (!(GATE_KINDS as readonly string[]).includes(kind)) {
		throw new GateFormatError(`${file}: unknown kind '${kind}' (expected one of: ${GATE_KINDS.join(", ")})`);
	}
	const status = required("status");
	if (!(GATE_STATUSES as readonly string[]).includes(status)) {
		throw new GateFormatError(`${file}: unknown status '${status}' (expected one of: ${GATE_STATUSES.join(", ")})`);
	}
	const stageRaw = optional("stage");
	let stage: number | null = null;
	if (stageRaw !== null) {
		if (!/^-?\d+$/.test(stageRaw)) throw new GateFormatError(`${file}: stage must be an integer, got '${stageRaw}'`);
		stage = Number.parseInt(stageRaw, 10);
	}
	if (contextRefs.some((r) => r === "")) {
		throw new GateFormatError(`${file}: context_refs must be a list of non-empty strings`);
	}
	const createdAt = required("created_at");
	if (!isIsoTimestamp(createdAt)) {
		throw new GateFormatError(`${file}: created_at is not an ISO-8601 timestamp: '${createdAt}'`);
	}
	const answeredAt = optional("answered_at");
	if (answeredAt !== null && !isIsoTimestamp(answeredAt)) {
		throw new GateFormatError(`${file}: answered_at is not an ISO-8601 timestamp: '${answeredAt}'`);
	}
	required("created_by");
	const question = required("question");

	return {
		id,
		kind,
		status,
		stage,
		key: optional("key"),
		question,
		createdAt,
		path: file,
	};
}

/** All gates in the directory, ordered by seq — the directory scan IS the
 * queue (D-105). A missing directory is an empty queue. Corrupt gate files
 * are reported in `errors` (the console surfaces them as warnings) and
 * excluded from the list, mirroring gates.py enumerate()'s explicit errors. */
export function listGates(projectDir: string): { gates: GateRecord[]; errors: string[] } {
	const dir = gatesDir(projectDir);
	const errors: string[] = [];
	const found: Array<{ seq: number; gate: GateRecord }> = [];
	let entries: fs.Dirent[];
	try {
		entries = fs.readdirSync(dir, { withFileTypes: true });
	} catch {
		return { gates: [], errors: [] };
	}
	for (const entry of entries) {
		const m = GATE_FILE_RE.exec(entry.name);
		if (m === null || !entry.isFile()) continue; // non-gate files and leftover .tmp files
		const file = path.join(dir, entry.name);
		let text: string;
		try {
			text = fs.readFileSync(file, "utf8");
		} catch (err) {
			errors.push(`${file}: ${String(err)}`);
			continue;
		}
		try {
			const gate = parseGateFile(text, file);
			if (gate.id !== entry.name.replace(/\.md$/, "")) {
				errors.push(`${file}: frontmatter id '${gate.id}' does not match file name`);
				continue;
			}
			found.push({ seq: Number(m[1]), gate });
		} catch (err) {
			errors.push(err instanceof Error ? err.message : String(err));
		}
	}
	found.sort((a, b) => a.seq - b.seq || a.gate.id.localeCompare(b.gate.id));
	return { gates: found.map((f) => f.gate), errors };
}

// ── timeline (mirror of autopilot/timeline.py query_events, D-109) ──────────

/** Event type vocabulary (D-109). Used for the console's default beat-free
 * include-set — NOT for rejection: unknown ev values parse fine. */
export const EVENT_TYPES = new Set([
	"beat",
	"dispatch",
	"worker-terminal",
	"advance",
	"gate-created",
	"gate-answered",
	"stalled",
	"skip",
	"stage-close",
	"config",
	"goal-halt",
	"goal-snapshot",
	"type-rejected",
	"reconcile",
	"resume",
	"l3-no-verdict",
]);

export const BEAT_EV = "beat";

/** The default timeline view's include-set: every event type except beats. */
export function nonBeatFilter(): Set<string> {
	const filter = new Set(EVENT_TYPES);
	filter.delete(BEAT_EV);
	return filter;
}

export interface TimelineEvent {
	ts: string;
	seq: number;
	ev: string;
	key: string;
	stage: number | null;
	detail: string;
}

export interface TimelineQuery {
	/** Parsed lines with seq > watermark, sorted ascending (rotations
	 * oldest → newest, then the current file). */
	events: TimelineEvent[];
	/** Events past the watermark that rotation no longer retains (超 2 代轮
	 * 转) — never a silent gap. */
	pruned: number;
	/** Unparseable (torn) lines encountered — counted, not silently dropped. */
	skipped: number;
	/** Highest-seq event in the retained chain — the watermark to persist
	 * (D-109: every status/timeline view stores {seq, ts}). */
	head: { seq: number; ts: string } | undefined;
}

/** Rotated generations, oldest → newest (`.N` → `.1`). Discovered by
 * directory scan so queries keep working whatever the retention is. */
function rotationChain(timelinePath: string): string[] {
	const dir = path.dirname(timelinePath);
	const prefix = `${path.basename(timelinePath)}.`;
	let entries: fs.Dirent[];
	try {
		entries = fs.readdirSync(dir, { withFileTypes: true });
	} catch {
		return [];
	}
	const found: Array<{ gen: number; file: string }> = [];
	for (const entry of entries) {
		if (!entry.name.startsWith(prefix)) continue;
		const suffix = entry.name.slice(prefix.length);
		if (/^\d+$/.test(suffix) && entry.isFile()) {
			found.push({ gen: Number(suffix), file: path.join(dir, entry.name) });
		}
	}
	found.sort((a, b) => b.gen - a.gen); // higher generation = older
	return found.map((f) => f.file);
}

function readTimelineEvents(file: string): { events: TimelineEvent[]; skipped: number } {
	let data: Buffer;
	try {
		data = fs.readFileSync(file);
	} catch {
		return { events: [], skipped: 0 }; // unreadable/absent file contributes nothing
	}
	const events: TimelineEvent[] = [];
	let skipped = 0;
	for (const raw of data.toString("utf8").split("\n")) {
		const line = raw.trim();
		if (line === "") continue;
		let obj: unknown;
		try {
			obj = JSON.parse(line);
		} catch {
			skipped += 1; // torn line (mid-write crash) — counted, never hidden
			continue;
		}
		if (typeof obj !== "object" || obj === null) {
			skipped += 1;
			continue;
		}
		const rec = obj as Record<string, unknown>;
		const seq = rec.seq;
		if (typeof seq !== "number" || !Number.isInteger(seq)) {
			skipped += 1;
			continue;
		}
		events.push({
			ts: typeof rec.ts === "string" ? rec.ts : "",
			seq,
			ev: typeof rec.ev === "string" ? rec.ev : "",
			key: typeof rec.key === "string" ? rec.key : "-",
			stage: typeof rec.stage === "number" && Number.isInteger(rec.stage) ? rec.stage : null,
			detail: typeof rec.detail === "string" ? rec.detail : "",
		});
	}
	return { events, skipped };
}

/** Replay timeline events with seq > watermark (D-109 回放协议): rotated
 * generations oldest → newest, then the current file; union filtered by seq,
 * sorted ascending. `evFilter` is an include-set (pass nonBeatFilter() for
 * the console's default beat-free view; undefined keeps every type).
 *
 * A watermark predating the oldest retained line yields a non-zero `pruned`
 * count — the replay explicitly reports what rotation ate instead of
 * silently starting mid-history. */
export function queryTimeline(timelinePath: string, watermark: number, evFilter?: ReadonlySet<string>): TimelineQuery {
	const mark = Number.isInteger(watermark) && watermark > 0 ? watermark : 0;
	const all: TimelineEvent[] = [];
	let skipped = 0;
	for (const source of [...rotationChain(timelinePath), timelinePath]) {
		const result = readTimelineEvents(source);
		all.push(...result.events);
		skipped += result.skipped;
	}
	all.sort((a, b) => a.seq - b.seq);
	const last = all.length > 0 ? all[all.length - 1] : undefined;
	let pruned: number;
	if (all.length > 0) {
		pruned = Math.max(0, all[0].seq - mark - 1);
	} else {
		// Empty chain but a positive watermark: everything the console ever
		// saw is gone — report at least the watermark's worth (lower bound).
		pruned = mark > 0 ? mark : 0;
	}
	const events = all.filter((e) => e.seq > mark && (evFilter === undefined || evFilter.has(e.ev)));
	return { events, pruned, skipped, head: last === undefined ? undefined : { seq: last.seq, ts: last.ts } };
}

/** Map an --since ISO timestamp onto the seq watermark protocol: the highest
 * seq among events at-or-before that timestamp (0 = replay everything). */
export function watermarkFromSince(timelinePath: string, sinceIso: string): number {
	const since = Date.parse(sinceIso);
	if (Number.isNaN(since)) return 0;
	let mark = 0;
	for (const source of [...rotationChain(timelinePath), timelinePath]) {
		for (const ev of readTimelineEvents(source).events) {
			const ts = Date.parse(ev.ts);
			if (!Number.isNaN(ts) && ts <= since && ev.seq > mark) mark = ev.seq;
		}
	}
	return mark;
}

// ── rounds (parity with autopilot/state.py used_rounds, VC-020) ──────────────

const TASK_FM_LINE_RE = /^([A-Za-z_][A-Za-z0-9_-]*):[ \t]*(.*?)[ \t]*$/;

/** Frontmatter scalar labels of one task.md (loop/attempt/origin/type...).
 * Lenient mirror of state.py parse_task_labels: a missing frontmatter or a
 * malformed line simply yields no label; nested blocks (read_scope lists)
 * are skipped, not parsed. */
export function parseTaskLabels(taskMdPath: string): Map<string, string> {
	let text: string;
	try {
		text = fs.readFileSync(taskMdPath, "utf8");
	} catch {
		return new Map();
	}
	const lines = text.split(/\r\n|\r|\n/);
	if (lines.length === 0 || lines[0].trim() !== "---") return new Map();
	const labels = new Map<string, string>();
	for (let i = 1; i < lines.length; i++) {
		const line = lines[i];
		if (line.trim() === "---") break;
		const m = TASK_FM_LINE_RE.exec(line);
		if (m === null) continue;
		labels.set(m[1] ?? "", m[2] ?? "");
	}
	return labels;
}

/** Per-loop used-round counts from task.md loop/attempt labels — the VC-020
 * parity surface with state.py used_rounds. A round = one distinct attempt
 * value within a loop (D-111 round table): same-attempt repair dispatches
 * and orphan re-insertions do not add rounds. A task.md whose attempt label
 * is missing degrades to file-count semantics keyed by its directory, so
 * rewrites of the same dir never double-count. In-flight dispatches count —
 * their task.md exists from the dispatch transaction on (D-102). */
export function usedRounds(workersDirs: string[]): Map<string, number> {
	const units = new Map<string, Set<string>>();
	for (const workersDir of workersDirs) {
		let entries: fs.Dirent[];
		try {
			entries = fs.readdirSync(workersDir, { withFileTypes: true });
		} catch {
			continue; // owner has no workers/ dir
		}
		const names = entries
			.filter((e) => e.isDirectory())
			.map((e) => e.name)
			.sort();
		for (const name of names) {
			const labels = parseTaskLabels(path.join(workersDir, name, "task.md"));
			const loop = labels.get("loop");
			if (loop === undefined || loop === "") continue;
			const attempt = (labels.get("attempt") ?? "").trim();
			const unit = attempt !== "" ? attempt : `@${name}`;
			let attempts = units.get(loop);
			if (attempts === undefined) {
				attempts = new Set();
				units.set(loop, attempts);
			}
			attempts.add(unit);
		}
	}
	const result = new Map<string, number>();
	for (const [loop, attempts] of units) result.set(loop, attempts.size);
	return result;
}

// ── the status model (D-005: derived from files only) ────────────────────────

export const STATUS_SCHEMA = "autopilot-status/1";

export interface RoundBudget {
	used: number;
	max: number;
}

export interface KeyRounds {
	l2: RoundBudget;
	l3: RoundBudget;
	retry: RoundBudget;
}

export interface StageKeyView {
	key: string;
	phase: string;
	state: string;
	rounds: KeyRounds;
}

export interface StageView {
	current: number;
	status: string;
	keys: StageKeyView[];
}

export interface GateView {
	id: string;
	kind: string;
	status: string;
}

export interface TimelineWatermark {
	seq: number;
	ts: string;
}

export interface StatusConfigView {
	enabled: boolean;
	poll_interval_sec: number;
	round_budget: number;
	max_parallel_keys: number;
}

/** The versioned `/autopilot status --json` payload (design §4.1, D-109 N8).
 * Field set and shapes are locked by the design example. */
export interface AutopilotStatus {
	schema: typeof STATUS_SCHEMA;
	stage: StageView;
	gates: GateView[];
	timeline: TimelineWatermark;
	config: StatusConfigView;
}

/** Derivation outcome: `status` is the schema-exact JSON surface; `paused`
 * and `warnings` are human-view extras (the D-110 pause flag lives in the
 * config file, not the versioned status schema). */
export interface StatusModel {
	status: AutopilotStatus;
	paused: boolean;
	warnings: string[];
}

export type StatusModelResult = { ok: true; model: StatusModel } | { ok: false; error: string };

/** The stage the conductor is currently driving: the running stage; else the
 * first stage not yet closed (pending/approved/halted — halted still awaits
 * a human decision, so it stays current); else the last stage (everything
 * closed — a terminal view). Undefined when there is no roadmap. */
function currentStage(stages: RoadmapStage[]): RoadmapStage | undefined {
	if (stages.length === 0) return undefined;
	const running = stages.find((s) => s.status === "running");
	if (running !== undefined) return running;
	const open = stages.find((s) => s.status !== "closed" && s.status !== "closed-human");
	return open ?? stages[stages.length - 1];
}

/** Aggregate a key's per-loop used rounds into the three families the status
 * schema exposes: `l2:{key}:{edge}` → l2, `l3:{key}` → l3, `exec:{key}:{stem}`
 * and `repair:{key}` → retry. A family's used value is its most-consumed
 * loop — budgets are enforced per loop (AC-008/AC-011), so the maximum is
 * the binding constraint. max = config round_budget for every family. */
function keyRounds(perLoop: Map<string, number>, key: string, budget: number): KeyRounds {
	let l2 = 0;
	let l3 = 0;
	let retry = 0;
	for (const [loop, used] of perLoop) {
		if (loop.startsWith(`l2:${key}:`)) l2 = Math.max(l2, used);
		else if (loop === `l3:${key}`) l3 = Math.max(l3, used);
		else if (loop.startsWith(`exec:${key}:`) || loop === `repair:${key}`) retry = Math.max(retry, used);
	}
	return {
		l2: { used: l2, max: budget },
		l3: { used: l3, max: budget },
		retry: { used: retry, max: budget },
	};
}

/** Derive the full status view from files alone (AC-015: a reopened console
 * rebuilds this in <10s with zero process state). The only hard failure is
 * an invalid config.json (D-110 fail-closed); a missing/parse-failed
 * roadmap, corrupt gate files, and an absent timeline all degrade to empty
 * views plus warnings. */
export function deriveStatusModel(projectDir: string): StatusModelResult {
	const cfg = readConfig(projectDir);
	if (!cfg.ok) return cfg;
	const config = cfg.config;

	const warnings: string[] = [];
	const roadmap = readRoadmap(projectDir);
	if (roadmap.ok) {
		warnings.push(...roadmap.warnings);
	} else {
		warnings.push(roadmap.error);
	}
	const stage = currentStage(roadmap.ok ? roadmap.stages : []);

	const agenticdoc = path.join(projectDir, ".agenticdoc");
	const phaseByKey = new Map(new IndexStore(agenticdoc).readAll().map((e) => [e.key, e.phase]));

	const keys: StageKeyView[] = [];
	if (stage !== undefined) {
		for (const row of stage.keys) {
			const perLoop = usedRounds([path.join(agenticdoc, row.key, "workers")]);
			keys.push({
				key: row.key,
				phase: phaseByKey.get(row.key) ?? "—",
				// key-status line absent (fresh proposal) → the only non-terminal
				// enum value, "running" (D-105 KEY_STATUSES has no "pending").
				state: stage.keyStatus[row.key] ?? "running",
				rounds: keyRounds(perLoop, row.key, config.round_budget),
			});
		}
	}

	const gateScan = listGates(projectDir);
	warnings.push(...gateScan.errors);
	const gates: GateView[] = gateScan.gates.map((g) => ({ id: g.id, kind: g.kind, status: g.status }));

	const head = queryTimeline(timelinePath(projectDir), 0).head;

	return {
		ok: true,
		model: {
			status: {
				schema: STATUS_SCHEMA,
				stage: {
					current: stage === undefined ? 0 : stage.number,
					status: stage === undefined ? "none" : stage.status,
					keys,
				},
				gates,
				timeline: head === undefined ? { seq: 0, ts: "" } : { seq: head.seq, ts: head.ts },
				config: {
					enabled: config.enabled,
					poll_interval_sec: config.poll_interval_sec,
					round_budget: config.round_budget,
					max_parallel_keys: config.max_parallel_keys,
				},
			},
			paused: config.paused,
			warnings,
		},
	};
}

/** Human-readable rendering of the SAME derivation that produced the --json
 * payload (view parity, VC-017): every number below is taken from the model
 * object, so the two views cannot drift. */
export function renderStatusText(model: StatusModel): string {
	const { status, paused, warnings } = model;
	const lines: string[] = [];
	if (status.stage.current > 0) {
		lines.push(`stage ${status.stage.current} (${status.stage.status})`);
		for (const k of status.stage.keys) {
			lines.push(
				`  ${k.key} | phase=${k.phase} | state=${k.state} | L2 ${k.rounds.l2.used}/${k.rounds.l2.max}` +
					` | L3 ${k.rounds.l3.used}/${k.rounds.l3.max} | retry ${k.rounds.retry.used}/${k.rounds.retry.max}`,
			);
		}
		if (status.stage.keys.length === 0) lines.push("  (no keys)");
	} else {
		lines.push("stage: none (no roadmap — autopilot not initialized or no stages parsed)");
	}
	const pending = status.gates.filter((g) => g.status === "pending");
	lines.push(`gates: ${status.gates.length} total, ${pending.length} pending`);
	for (const g of status.gates) lines.push(`  ${g.id} ${g.kind} ${g.status}`);
	lines.push(`timeline: seq=${status.timeline.seq} ts=${status.timeline.ts}`);
	lines.push(
		`config: enabled=${status.config.enabled} | poll_interval_sec=${status.config.poll_interval_sec}` +
			` | round_budget=${status.config.round_budget} | max_parallel_keys=${status.config.max_parallel_keys}` +
			`${paused ? " | paused" : ""}`,
	);
	for (const w of warnings) lines.push(`warning: ${w}`);
	return lines.join("\n");
}
