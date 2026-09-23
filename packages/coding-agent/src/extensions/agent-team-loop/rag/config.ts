/**
 * RAG configuration layer (mw-rag-integration T-01; design D-003/D-009/D-013,
 * VC-002/VC-024): two-layer (machine + project) per-field merge, validation,
 * default/required resolution and the static-config fingerprint.
 *
 * Pure decision logic: fs reads only (rag-servers.yml, target.yml, path_roots
 * digest) — no writes, no network. The Python side
 * (mw_common.load_rag_config, T-06) mirrors this module 1:1 so both sides read
 * the same bytes.
 *
 * YAML shape: every YAML input key is snake_case (`token_env` / `timeout_ms` /
 * `path_roots_file` / `cli_entry`, and `target.yml`'s `default_server` /
 * `chat_budget` / `time_budget_s`) so both languages read one file;
 * RagServerEntry / RagRoleSpec expose camelCase, while `origin` keeps the
 * snake_case evaluated field paths (`mcp.url`, `path_roots_file`, …) that the
 * Python side (mw_common.RAG_FIELD_CAMEL) records.
 *
 * Resolution precedence (D-003/D-013, task T-01):
 *   machine file: MW_RAG_SERVERS_FILE > MW_RAG_SERVERS_HOME/.agents >
 *   $HOME/.agents > %USERPROFILE%/.agents; a missing file/dir is an empty
 *   layer and is never created (D-014).
 *   servers: machine layer, then project layer field-by-field (project value
 *   wins; arrays replace wholesale; `null` deletes the field).
 */

import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { parse } from "yaml";
import { rawTargetYml } from "../shared/target-config.ts";

/** Env override for the machine service table file (whole-file hook). */
export const ENV_RAG_SERVERS_FILE = "MW_RAG_SERVERS_FILE";
/** Env override for the machine service table directory. */
export const ENV_RAG_SERVERS_HOME = "MW_RAG_SERVERS_HOME";
/** Machine service table basename under `<home>/.agents/`. */
export const RAG_SERVERS_BASENAME = "rag-servers.yml";
/** Default per-call transport timeout (design D-006). */
export const DEFAULT_RAG_TIMEOUT_MS = 180_000;
/** Default rag_chat call budget (design D-006). */
export const DEFAULT_RAG_CHAT_BUDGET = 2;
/** Default task-level cumulative RAG time budget in seconds (D-006). */
export const DEFAULT_RAG_TIME_BUDGET_S = 900;
/**
 * snake_case (YAML) -> camelCase (runtime) field mapping. mw_common
 * `RAG_FIELD_CAMEL` is the authoritative copy; the two tables must stay
 * identical (T-01/T-06 parity). Fingerprint payloads and `origin` keys stay
 * snake_case, so this only describes the user-facing `RagConfig` shape.
 */
export const RAG_FIELD_CAMEL: Record<string, string> = {
	token_env: "tokenEnv",
	timeout_ms: "timeoutMs",
	cli_entry: "cliEntry",
	path_roots_file: "pathRootsFile",
	default_server: "defaultServer",
	chat_budget: "chatBudget",
	time_budget_s: "timeBudgetS",
};

export type RagTransport = "mcp" | "skill" | "both";

/** Error categories — parity-asserted by kind, not by message text. */
export type RagConfigErrorKind =
	| "bad-yaml"
	| "invalid-shape"
	| "unknown-key"
	| "unknown-server"
	| "mcp-missing-url"
	| "skill-missing-cli"
	| "enabled-empty-entry";

export class RagConfigError extends Error {
	readonly kind: RagConfigErrorKind;

	constructor(kind: RagConfigErrorKind, message: string) {
		super(message);
		this.name = "RagConfigError";
		this.kind = kind;
	}
}

function fail(kind: RagConfigErrorKind, message: string): never {
	throw new RagConfigError(kind, message);
}

export interface RagMcpEntry {
	url: string;
	tokenEnv: string | null;
	timeoutMs: number;
}

export interface RagSkillEntry {
	/** `skill.dir`: control-workspace-relative (or absolute); `null` = the control root (D-301). */
	dir: string | null;
	cliEntry: string;
	timeoutMs: number;
}

export interface RagCapabilities {
	graph: boolean;
	chat: boolean;
	rewrite: boolean;
}

export type RagFieldOrigin = "machine" | "project";

export interface RagServerEntry {
	transport: RagTransport;
	mcp: RagMcpEntry | null;
	skill: RagSkillEntry | null;
	adapter: "overcode-v1";
	pathRootsFile: string | null;
	/** sha256 of the resolved `path_roots_file` bytes (project-root anchored). */
	pathRootsDigest: string | null;
	sources: string[];
	capabilities: RagCapabilities;
	/** Per evaluated field path (`mcp.url`, `sources`, `skill`, …) origin. */
	origin: Record<string, RagFieldOrigin>;
}

export interface RagRoleSpec {
	server?: string;
	source?: string;
	require?: boolean;
	rewrite?: boolean;
	chatBudget?: number;
	timeBudgetS?: number;
}

export interface RagPhaseSpec {
	server?: string;
	source?: string;
	require?: boolean;
	rewrite?: boolean;
}

/** Global budget defaults from `target.yml`'s `rag.budgets` section. */
export interface RagBudgets {
	chat: number;
	timeS: number;
}

export interface RagConfig {
	enabled: string[];
	defaultServer: string | null;
	servers: Record<string, RagServerEntry>;
	roles: Record<string, RagRoleSpec>;
	phases: Record<string, RagPhaseSpec>;
	budgets: RagBudgets;
	fingerprint: string;
}

// ── guards (unknown + narrowing; never `any`) ───────────────────────────────

function isObject(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asObject(value: unknown, field: string): Record<string, unknown> {
	if (!isObject(value)) fail("invalid-shape", `rag config: field '${field}' must be a mapping`);
	return value;
}

function requireString(value: unknown, field: string): string {
	if (typeof value !== "string" || value.trim() === "") {
		fail("invalid-shape", `rag config: field '${field}' must be a non-empty string`);
	}
	return value;
}

function optionalString(value: unknown, field: string): string | null {
	return value === undefined || value === null ? null : requireString(value, field);
}

/**
 * Python `_rag_finalize_mcp`/`_rag_finalize_skill` store `.strip()`ed values
 * (`mw_common.py:534-538,564-565`), while `requireString` only *rejects*
 * whitespace-only input and keeps the padding. Trimming here keeps the
 * fingerprint byte-identical for a padded value (T-4 finding 3, AC-302).
 */
function optionalTrimmedString(value: unknown, field: string): string | null {
	const raw = optionalString(value, field);
	return raw === null ? null : raw.trim();
}

function optionalBoolean(value: unknown, field: string, fallback: boolean): boolean {
	if (value === undefined || value === null) return fallback;
	if (typeof value !== "boolean") fail("invalid-shape", `rag config: field '${field}' must be a boolean`);
	return value;
}

function optionalNumber(value: unknown, field: string, fallback: number): number {
	if (value === undefined || value === null) return fallback;
	if (typeof value !== "number" || !Number.isFinite(value)) {
		fail("invalid-shape", `rag config: field '${field}' must be a number`);
	}
	return value;
}

function stringArray(value: unknown, field: string): string[] {
	if (value === undefined || value === null) return [];
	if (!Array.isArray(value)) fail("invalid-shape", `rag config: field '${field}' must be a list of strings`);
	return value.map((entry) => requireString(entry, field));
}

function checkKeys(value: Record<string, unknown>, allowed: Set<string>, where: string): void {
	const extra = Object.keys(value).filter((key) => !allowed.has(key));
	if (extra.length > 0) {
		fail(
			"unknown-key",
			`rag config: unexpected key(s) in ${where}: ${extra.join(", ")} (allowed: ${[...allowed].join(", ")})`,
		);
	}
}

// ── machine layer path (D-013) ──────────────────────────────────────────────

/**
 * Resolve the machine service table path (D-013): MW_RAG_SERVERS_FILE (whole
 * file) > MW_RAG_SERVERS_HOME (dir) > $HOME > %USERPROFILE%; the target is
 * `<home>/.agents/rag-servers.yml`. Returns "" when no home can be resolved
 * (the caller treats that as an empty layer). The directory is never created.
 */
export function machineRagServersPath(env: NodeJS.ProcessEnv = process.env): string {
	const explicitFile = env[ENV_RAG_SERVERS_FILE]?.trim();
	if (explicitFile !== undefined && explicitFile !== "") return explicitFile;
	const home = env[ENV_RAG_SERVERS_HOME]?.trim() || env.HOME?.trim() || env.USERPROFILE?.trim();
	if (home === undefined || home === "") return "";
	return path.join(home, ".agents", RAG_SERVERS_BASENAME);
}

// ── per-field merge (D-003, VC-024) ─────────────────────────────────────────

const RAG_SERVERS_TOP_KEYS = new Set(["servers"]);
const RAG_SECTION_KEYS = new Set(["enabled", "default_server", "roles", "phases", "budgets"]);
/** Merge order mirrors mw_common._RAG_SERVER_FIELDS. */
const SERVER_FIELDS = ["transport", "adapter", "path_roots_file", "sources", "capabilities", "mcp", "skill"] as const;
const SERVER_KEYS = new Set<string>(SERVER_FIELDS);
const MCP_KEYS = new Set(["url", "token_env", "timeout_ms"]);
const SKILL_KEYS = new Set(["dir", "cli_entry", "timeout_ms"]);
const CAPABILITY_KEYS = new Set(["graph", "chat", "rewrite"]);
const NESTED_FIELDS: Record<string, Set<string>> = {
	mcp: MCP_KEYS,
	skill: SKILL_KEYS,
	capabilities: CAPABILITY_KEYS,
};
const ROLE_KEYS = new Set(["server", "source", "require", "rewrite", "chat_budget", "time_budget_s"]);
const PHASE_KEYS = new Set(["server", "source", "require", "rewrite"]);
const BUDGET_KEYS = new Set(["chat_budget", "time_budget_s"]);

function parseTransport(value: unknown, field: string): RagTransport {
	if (value === "mcp" || value === "skill" || value === "both") return value;
	fail("invalid-shape", `rag config: field '${field}' must be one of 'mcp', 'skill', 'both'`);
}

function nestedBlockValue(value: unknown, field: string, name: string): Record<string, unknown> | null {
	if (value === undefined || value === null) return null;
	return asObject(value, `server '${name}'.${field}`);
}

function parseMcp(raw: Record<string, unknown> | null, name: string): RagMcpEntry | null {
	if (raw === null) return null;
	const url = optionalTrimmedString(raw.url, `server '${name}'.mcp.url`);
	if (url === null) fail("mcp-missing-url", `rag server '${name}': mcp.url is required`);
	return {
		url,
		tokenEnv: optionalTrimmedString(raw.token_env, `server '${name}'.mcp.token_env`),
		timeoutMs: optionalNumber(raw.timeout_ms, `server '${name}'.mcp.timeout_ms`, DEFAULT_RAG_TIMEOUT_MS),
	};
}

function parseSkill(raw: Record<string, unknown> | null, name: string): RagSkillEntry | null {
	if (raw === null) return null;
	// D-301/AC-301: a missing/null `dir` means the control workspace root.
	// The parsed value stays `null` (never `"."`) so `ragFingerprint` keeps
	// byte parity with `mw_common._rag_finalize_skill`/`rag_fingerprint`.
	const dir = optionalTrimmedString(raw.dir, `server '${name}'.skill.dir`);
	const cliEntry = optionalTrimmedString(raw.cli_entry, `server '${name}'.skill.cli_entry`);
	if (cliEntry === null) fail("skill-missing-cli", `rag server '${name}': skill.cli_entry is required`);
	return {
		dir,
		cliEntry,
		timeoutMs: optionalNumber(raw.timeout_ms, `server '${name}'.skill.timeout_ms`, DEFAULT_RAG_TIMEOUT_MS),
	};
}

function parseCapabilities(raw: Record<string, unknown> | null, name: string): RagCapabilities {
	if (raw === null) return { graph: false, chat: false, rewrite: false };
	return {
		graph: optionalBoolean(raw.graph, `server '${name}'.capabilities.graph`, false),
		chat: optionalBoolean(raw.chat, `server '${name}'.capabilities.chat`, false),
		rewrite: optionalBoolean(raw.rewrite, `server '${name}'.capabilities.rewrite`, false),
	};
}

/**
 * Merge one server entry from the machine and project layers (D-003), mirroring
 * mw_common._rag_merge_server field by field: scalars merge per key, nested
 * blocks merge key by key (a project `null` sub-key deletes it), `sources`
 * replaces wholesale, a project `null` deletes a field/block and a machine
 * `null` deletes nothing. `origin` carries the snake_case evaluated field path
 * of every contributed key (`mcp.url`, `path_roots_file`, …). `transport`
 * defaults to `mcp` (Python parity) instead of being inferred from the present
 * blocks. Fail-closed on unknown keys and missing url/cli_entry.
 */
export function mergeServerEntry(machine: unknown, project: unknown, name: string): RagServerEntry {
	const machineObj =
		machine === undefined || machine === null ? null : asObject(machine, `server '${name}' (machine)`);
	const projectObj =
		project === undefined || project === null ? null : asObject(project, `server '${name}' (project)`);
	if (machineObj !== null) checkKeys(machineObj, SERVER_KEYS, `server '${name}' (machine)`);
	if (projectObj !== null) checkKeys(projectObj, SERVER_KEYS, `server '${name}' (project)`);

	const machineRecord: Record<string, unknown> = machineObj ?? {};
	const projectRecord: Record<string, unknown> = projectObj ?? {};
	const origin: Record<string, RagFieldOrigin> = {};
	const merged: Record<string, unknown> = {};
	for (const field of SERVER_FIELDS) {
		const inMachine = field in machineRecord;
		const inProject = field in projectRecord;
		if (!inMachine && !inProject) continue;
		const machineValue = inMachine ? machineRecord[field] : undefined;
		const projectValue = inProject ? projectRecord[field] : undefined;
		if (inProject && projectValue === null) {
			merged[field] = null;
			origin[field] = "project";
			continue;
		}
		if (inMachine && machineValue === null && !inProject) continue;
		const nestedFields = NESTED_FIELDS[field];
		if (nestedFields !== undefined) {
			const nested: Record<string, unknown> = {};
			if (inMachine && machineValue !== undefined && machineValue !== null) {
				const machineBlock = asObject(machineValue, `server '${name}'.${field} (machine)`);
				checkKeys(machineBlock, nestedFields, `server '${name}'.${field} (machine)`);
				for (const key of Object.keys(machineBlock)) {
					nested[key] = machineBlock[key];
					origin[`${field}.${key}`] = "machine";
				}
			}
			if (inProject && projectValue !== undefined && projectValue !== null) {
				const projectBlock = asObject(projectValue, `server '${name}'.${field} (project)`);
				checkKeys(projectBlock, nestedFields, `server '${name}'.${field} (project)`);
				for (const key of Object.keys(projectBlock)) {
					if (projectBlock[key] === null) delete nested[key];
					else nested[key] = projectBlock[key];
					origin[`${field}.${key}`] = "project";
				}
			}
			merged[field] = Object.keys(nested).length > 0 ? nested : null;
			continue;
		}
		if (inProject) {
			merged[field] = projectValue;
			origin[field] = "project";
		} else {
			merged[field] = machineValue;
			origin[field] = "machine";
		}
	}

	const rawTransport = merged.transport;
	const transport =
		rawTransport === undefined || rawTransport === null
			? "mcp"
			: parseTransport(rawTransport, `server '${name}'.transport`);

	let adapter = "overcode-v1";
	if (merged.adapter !== undefined && merged.adapter !== null) {
		adapter = requireString(merged.adapter, `server '${name}'.adapter`);
	}
	if (adapter !== "overcode-v1") {
		fail("invalid-shape", `rag server '${name}': unsupported adapter '${adapter}' (only 'overcode-v1')`);
	}

	// NOTE: Python keeps the *raw* value here (its field is stripped, but the
	// digest at `mw_common.py:637` is computed from the untrimmed string), so
	// this one field is deliberately left untrimmed; see 遗留 R-6.
	const pathRootsFile = optionalString(merged.path_roots_file, `server '${name}'.path_roots_file`);
	const sources = stringArray(merged.sources, `server '${name}'.sources`);
	const mcp = parseMcp(nestedBlockValue(merged.mcp, "mcp", name), name);
	const skill = parseSkill(nestedBlockValue(merged.skill, "skill", name), name);
	const capabilities = parseCapabilities(nestedBlockValue(merged.capabilities, "capabilities", name), name);

	if ((transport === "mcp" || transport === "both") && mcp === null) {
		fail("mcp-missing-url", `rag server '${name}': transport '${transport}' requires an 'mcp' block with a url`);
	}
	if ((transport === "skill" || transport === "both") && skill === null) {
		fail(
			"skill-missing-cli",
			`rag server '${name}': transport '${transport}' requires a 'skill' block with a cli_entry`,
		);
	}

	return {
		transport,
		mcp,
		skill,
		adapter: "overcode-v1",
		pathRootsFile,
		pathRootsDigest: null,
		sources,
		capabilities,
		origin,
	};
}

// ── file loading ────────────────────────────────────────────────────────────

/** Read a YAML file into a top-level mapping; a missing/blank file is `{}`. */
function readYamlMapping(file: string, label: string): Record<string, unknown> {
	let text: string;
	try {
		text = fs.readFileSync(file, "utf-8");
	} catch {
		return {};
	}
	if (text.replace(/^\uFEFF/, "").trim() === "") return {};
	let parsed: unknown;
	try {
		parsed = parse(text);
	} catch (err) {
		fail("bad-yaml", `${label} is not valid YAML (${file}): ${err instanceof Error ? err.message : String(err)}`);
	}
	if (parsed === undefined || parsed === null) {
		fail("invalid-shape", `${label}: top level must be a mapping (${file})`);
	}
	if (!isObject(parsed)) fail("invalid-shape", `${label}: top level must be a mapping (${file})`);
	return parsed;
}

/** Read one service table (`servers:` mapping); "" / missing = empty layer. */
function readServersTable(file: string, label: string): Record<string, unknown> {
	if (file === "") return {};
	const raw = readYamlMapping(file, label);
	checkKeys(raw, RAG_SERVERS_TOP_KEYS, `${label} top level`);
	const servers = raw.servers;
	if (servers === undefined || servers === null) return {};
	return asObject(servers, `${label} 'servers'`);
}

function readRagSection(controlRoot: string): Record<string, unknown> {
	const rag = rawTargetYml(controlRoot).rag;
	if (rag === undefined || rag === null) return {};
	const section = asObject(rag, "target.yml 'rag'");
	checkKeys(section, RAG_SECTION_KEYS, "target.yml 'rag' section");
	return section;
}

function parseEnabled(value: unknown): string[] {
	if (value === undefined || value === null) return [];
	if (!Array.isArray(value)) fail("invalid-shape", "target.yml rag.enabled must be a list of server names");
	return value.map((entry) => {
		if (typeof entry !== "string") fail("invalid-shape", "target.yml rag.enabled must be a list of server names");
		if (entry.trim() === "") fail("enabled-empty-entry", "target.yml rag.enabled must not contain empty entries");
		return entry;
	});
}

function parseBudgets(value: unknown): RagBudgets {
	if (value === undefined || value === null) {
		return { chat: DEFAULT_RAG_CHAT_BUDGET, timeS: DEFAULT_RAG_TIME_BUDGET_S };
	}
	const raw = asObject(value, "target.yml rag.budgets");
	checkKeys(raw, BUDGET_KEYS, "target.yml rag.budgets");
	return {
		chat: optionalNumber(raw.chat_budget, "target.yml rag.budgets.chat_budget", DEFAULT_RAG_CHAT_BUDGET),
		timeS: optionalNumber(raw.time_budget_s, "target.yml rag.budgets.time_budget_s", DEFAULT_RAG_TIME_BUDGET_S),
	};
}

function parseRoleSpecs(value: unknown): Record<string, RagRoleSpec> {
	if (value === undefined || value === null) return {};
	const raw = asObject(value, "target.yml rag.roles");
	const out: Record<string, RagRoleSpec> = {};
	for (const [role, entry] of Object.entries(raw)) {
		if (entry === undefined || entry === null) continue;
		const spec = asObject(entry, `target.yml rag.roles.${role}`);
		checkKeys(spec, ROLE_KEYS, `target.yml rag.roles.${role}`);
		const parsed: RagRoleSpec = {};
		if (spec.server !== undefined && spec.server !== null) {
			parsed.server = requireString(spec.server, `rag.roles.${role}.server`);
		}
		if (spec.source !== undefined && spec.source !== null) {
			parsed.source = requireString(spec.source, `rag.roles.${role}.source`);
		}
		if (spec.require !== undefined && spec.require !== null) {
			parsed.require = optionalBoolean(spec.require, `rag.roles.${role}.require`, false);
		}
		if (spec.rewrite !== undefined && spec.rewrite !== null) {
			parsed.rewrite = optionalBoolean(spec.rewrite, `rag.roles.${role}.rewrite`, false);
		}
		if (spec.chat_budget !== undefined && spec.chat_budget !== null) {
			parsed.chatBudget = optionalNumber(spec.chat_budget, `rag.roles.${role}.chat_budget`, 0);
		}
		if (spec.time_budget_s !== undefined && spec.time_budget_s !== null) {
			parsed.timeBudgetS = optionalNumber(spec.time_budget_s, `rag.roles.${role}.time_budget_s`, 0);
		}
		out[role] = parsed;
	}
	return out;
}

function parsePhaseSpecs(value: unknown): Record<string, RagPhaseSpec> {
	if (value === undefined || value === null) return {};
	const raw = asObject(value, "target.yml rag.phases");
	const out: Record<string, RagPhaseSpec> = {};
	for (const [phase, entry] of Object.entries(raw)) {
		if (entry === undefined || entry === null) continue;
		const spec = asObject(entry, `target.yml rag.phases.${phase}`);
		checkKeys(spec, PHASE_KEYS, `target.yml rag.phases.${phase}`);
		const parsed: RagPhaseSpec = {};
		if (spec.server !== undefined && spec.server !== null) {
			parsed.server = requireString(spec.server, `rag.phases.${phase}.server`);
		}
		if (spec.source !== undefined && spec.source !== null) {
			parsed.source = requireString(spec.source, `rag.phases.${phase}.source`);
		}
		if (spec.require !== undefined && spec.require !== null) {
			parsed.require = optionalBoolean(spec.require, `rag.phases.${phase}.require`, false);
		}
		if (spec.rewrite !== undefined && spec.rewrite !== null) {
			parsed.rewrite = optionalBoolean(spec.rewrite, `rag.phases.${phase}.rewrite`, false);
		}
		out[phase] = parsed;
	}
	return out;
}

function unknownServer(name: string, visible: string[]): never {
	fail(
		"unknown-server",
		`unknown rag server '${name}' (visible: ${visible.length > 0 ? visible.join(", ") : "none"})`,
	);
}

/**
 * Load and merge the RAG configuration for a control root. No files → an
 * `enabled`-empty config (zero impact, D-014). Throws RagConfigError on
 * unknown keys/servers and on unusable mcp/skill blocks.
 */
export function loadRagConfig(controlRoot: string): RagConfig {
	const machineTable = readServersTable(machineRagServersPath(), "machine rag-servers.yml");
	const projectFile = path.join(controlRoot, ".mw", RAG_SERVERS_BASENAME);
	const projectTable = readServersTable(projectFile, "project rag-servers.yml");
	const rag = readRagSection(controlRoot);

	const names = [...new Set([...Object.keys(machineTable), ...Object.keys(projectTable)])].sort();
	const servers: Record<string, RagServerEntry> = {};
	for (const name of names) {
		const entry = mergeServerEntry(machineTable[name], projectTable[name], name);
		entry.pathRootsDigest = pathRootsDigest(controlRoot, entry.pathRootsFile);
		servers[name] = entry;
	}
	const visible = Object.keys(servers);

	const enabled = parseEnabled(rag.enabled);
	for (const name of enabled) {
		if (!(name in servers)) unknownServer(name, visible);
	}

	const defaultServer = optionalString(rag.default_server, "target.yml rag.default_server");
	if (defaultServer !== null && !(defaultServer in servers)) unknownServer(defaultServer, visible);

	const roles = parseRoleSpecs(rag.roles);
	for (const spec of Object.values(roles)) {
		if (spec.server !== undefined && !(spec.server in servers)) unknownServer(spec.server, visible);
	}
	const phases = parsePhaseSpecs(rag.phases);
	for (const spec of Object.values(phases)) {
		if (spec.server !== undefined && !(spec.server in servers)) unknownServer(spec.server, visible);
	}

	const budgets = parseBudgets(rag.budgets);
	const config: RagConfig = { enabled, defaultServer, servers, roles, phases, budgets, fingerprint: "" };
	config.fingerprint = ragFingerprint(config);
	return config;
}

// ── default / required resolution ───────────────────────────────────────────

/**
 * Roles/phases whose default `rewrite` is on when the server declares the
 * capability (AC-006 "research roles/phases"). `rag/adapter.ts` re-exports
 * `rewriteDefaults` and `mw_common.RAG_RESEARCH_ROLES` / `RAG_RESEARCH_PHASES`
 * mirror both sets.
 */
const RESEARCH_ROLES = new Set(["spec", "design", "research", "rag-research"]);
const RESEARCH_PHASES = new Set(["spec", "design"]);

/**
 * The single `rewrite` decision: an explicit role/phase `rewrite:` always
 * wins, otherwise the server capability gates a research role/phase. Used by
 * `resolveDefaults` (both `renderRagBlock` and `callRag`) and by the
 * `rag_search` wire-tool selection; there is no second implementation.
 */
export function rewriteDefaults(role: string, phase: string, capabilityRewrite: boolean, explicit?: boolean): boolean {
	if (explicit !== undefined) return explicit;
	const researchLike = RESEARCH_ROLES.has(role) || RESEARCH_PHASES.has(phase);
	return researchLike && capabilityRewrite;
}

/**
 * The single role/phase default resolver (D-102/D-104/D-109), shared by
 * `renderRagBlock` and `callRag`. Declared values only, authoritative
 * precedence `role > phase > defaultServer`: the role/phase specs are read
 * directly, never through a pre-resolved fallback, so a phase-declared server
 * is not shadowed by `default_server`. An empty/unregistered axis contributes
 * nothing (D-103): `server = defaultServer`, `source = null` and `rewrite`
 * reduces to `rewriteDefaults("", "", …)` = false. `rewrite` is the one
 * `rewriteDefaults` decision: explicit role/phase `rewrite:` wins, otherwise
 * the selected server's `capabilities.rewrite` combined with a research
 * role/phase (AC-006).
 */
export function resolveDefaults(
	config: RagConfig,
	role: string,
	phase: string,
): { server: string | null; source: string | null; rewrite: boolean } {
	const roleSpec = role !== "" ? config.roles[role] : undefined;
	const phaseSpec = phase !== "" ? config.phases[phase] : undefined;
	const server = roleSpec?.server ?? phaseSpec?.server ?? config.defaultServer ?? null;
	const source = roleSpec?.source ?? phaseSpec?.source ?? null;
	const explicit = roleSpec?.rewrite ?? phaseSpec?.rewrite;
	const capabilityRewrite = server !== null && config.servers[server]?.capabilities.rewrite === true;
	return { server, source, rewrite: rewriteDefaults(role, phase, capabilityRewrite, explicit) };
}

/** Required judgment is a union with no exceptions (design §2). */
export function requiredFor(config: RagConfig, role: string, phase: string): boolean {
	return config.roles[role]?.require === true || config.phases[phase]?.require === true;
}

// ── fingerprint (D-009, VC-022) ─────────────────────────────────────────────

function canonicalize(value: unknown): unknown {
	if (Array.isArray(value)) return value.map(canonicalize);
	if (isObject(value)) {
		const out: Record<string, unknown> = {};
		for (const key of Object.keys(value).sort()) out[key] = canonicalize(value[key]);
		return out;
	}
	return value;
}

function canonicalJson(value: unknown): string {
	return JSON.stringify(canonicalize(value));
}

function pathRootsDigest(controlRoot: string, file: string | null): string | null {
	if (file === null) return null;
	const target = path.isAbsolute(file) ? file : path.join(controlRoot, file);
	try {
		return createHash("sha256").update(fs.readFileSync(target)).digest("hex");
	} catch {
		return null;
	}
}

function roleSpecToSnake(spec: RagRoleSpec): Record<string, unknown> {
	const out: Record<string, unknown> = {};
	if (spec.server !== undefined) out.server = spec.server;
	if (spec.source !== undefined) out.source = spec.source;
	if (spec.require !== undefined) out.require = spec.require;
	if (spec.rewrite !== undefined) out.rewrite = spec.rewrite;
	if (spec.chatBudget !== undefined) out.chat_budget = spec.chatBudget;
	if (spec.timeBudgetS !== undefined) out.time_budget_s = spec.timeBudgetS;
	return out;
}

function phaseSpecToSnake(spec: RagPhaseSpec): Record<string, unknown> {
	const out: Record<string, unknown> = {};
	if (spec.server !== undefined) out.server = spec.server;
	if (spec.source !== undefined) out.source = spec.source;
	if (spec.require !== undefined) out.require = spec.require;
	if (spec.rewrite !== undefined) out.rewrite = spec.rewrite;
	return out;
}

/**
 * Static-config fingerprint (D-009, VC-022), byte-identical to
 * mw_common.rag_fingerprint: canonical JSON (sorted keys, no whitespace) over
 * only the enabled servers' static fields + the project-root-anchored
 * `path_roots` content digest, the roles/phases specs and the budgets.
 * Probe/health state, session ids and every field of a non-enabled server are
 * excluded, so an unrelated change or a server restart never looks like a
 * config tear. Roles/phases are hashed verbatim (never resolved against
 * defaults) and the payload keys are snake_case, exactly like the Python side.
 */
export function ragFingerprint(config: RagConfig, enabledOnly?: string[]): string {
	const names = [...new Set(enabledOnly ?? config.enabled)].sort();
	const servers = names.map((name) => {
		const entry = config.servers[name];
		if (entry === undefined) unknownServer(name, Object.keys(config.servers));
		return {
			name,
			transport: entry.transport,
			adapter: entry.adapter,
			mcp:
				entry.mcp === null
					? null
					: { url: entry.mcp.url, token_env: entry.mcp.tokenEnv, timeout_ms: entry.mcp.timeoutMs },
			skill:
				entry.skill === null
					? null
					: { dir: entry.skill.dir, cli_entry: entry.skill.cliEntry, timeout_ms: entry.skill.timeoutMs },
			path_roots_file: entry.pathRootsFile,
			path_roots_digest: entry.pathRootsDigest,
			sources: entry.sources,
			capabilities: entry.capabilities,
		};
	});
	const roles: Record<string, unknown> = {};
	for (const role of Object.keys(config.roles)) roles[role] = roleSpecToSnake(config.roles[role]);
	const phases: Record<string, unknown> = {};
	for (const phase of Object.keys(config.phases)) phases[phase] = phaseSpecToSnake(config.phases[phase]);
	const payload = {
		enabled: names,
		servers,
		default_server: config.defaultServer,
		roles,
		phases,
		budgets: { chat_budget: config.budgets.chat, time_budget_s: config.budgets.timeS },
	};
	return createHash("sha256").update(canonicalJson(payload)).digest("hex");
}
