import { randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { acquireLock } from "./file-lock.ts";
import { controlRootFromTaskPath } from "./paths.ts";
import { readTaskType } from "./task-frontmatter.ts";

export interface ContextCompactionPolicy {
	enabled: boolean;
	triggerRatio: number;
	targetRatio: number;
	keepRecentTokens: number;
	maxSummaryTokens: number;
	timeoutMs: number;
}

export const CONTEXT_POLICY_FIELDS = [
	"maxTokens",
	"compaction.enabled",
	"compaction.triggerRatio",
	"compaction.targetRatio",
	"compaction.keepRecentTokens",
	"compaction.maxSummaryTokens",
	"compaction.timeoutMs",
] as const;
export type ContextPolicyField = (typeof CONTEXT_POLICY_FIELDS)[number];
export const DELEGATED_CONTEXT_FIELDS: readonly ContextPolicyField[] = [
	"compaction.targetRatio",
	"compaction.keepRecentTokens",
	"compaction.maxSummaryTokens",
	"compaction.timeoutMs",
];
export type ContextPolicyScope = "global" | "project";

export interface ContextPolicySource {
	scope: ContextPolicyScope;
	level: "defaults" | "type";
	path: string;
	taskType?: string;
	builtin: boolean;
}

export interface ContextPolicyOverride {
	maxTokens?: number;
	compaction?: Partial<ContextCompactionPolicy>;
}

export interface ContextPolicyDocument {
	version: 1;
	defaults?: ContextPolicyOverride;
	types?: Record<string, ContextPolicyOverride>;
}

export interface ContextPolicyLocation {
	controlRoot: string;
	taskType?: string;
	taskFile?: string;
	homeDir?: string;
}

export interface ResolvedContextPolicy {
	version: 1;
	taskType: string;
	controlRoot: string;
	maxTokens: number;
	compaction: ContextCompactionPolicy;
	sources: Record<ContextPolicyField, ContextPolicySource>;
	paths: { global: string; project: string };
}

export class ContextPolicyError extends Error {
	readonly code: string;
	readonly path: string;
	readonly field: string;

	constructor(code: string, filePath: string, field: string, reason: string) {
		super(`${code}: ${filePath} [${field}]: ${reason}`);
		this.name = "ContextPolicyError";
		this.code = code;
		this.path = filePath;
		this.field = field;
	}
}

const DEFAULTS = {
	maxTokens: 512000,
	compaction: {
		enabled: true,
		triggerRatio: 0.8,
		targetRatio: 0.5,
		keepRecentTokens: 20000,
		maxSummaryTokens: 4096,
		timeoutMs: 120000,
	},
} satisfies Required<ContextPolicyOverride>;

function initialGlobalDocument(): ContextPolicyDocument {
	return {
		version: 1,
		defaults: {
			maxTokens: DEFAULTS.maxTokens,
			compaction: { enabled: DEFAULTS.compaction.enabled, triggerRatio: DEFAULTS.compaction.triggerRatio },
		},
		types: { coding: { maxTokens: 256000 }, research: { maxTokens: 256000 }, review: { maxTokens: 512000 } },
	};
}

function object(value: unknown, filePath: string, field: string): Record<string, unknown> {
	if (!value || typeof value !== "object" || Array.isArray(value))
		throw new ContextPolicyError("MW_CONTEXT_CONFIG_INVALID", filePath, field, "expected an object");
	return value as Record<string, unknown>;
}

function knownFields(
	value: Record<string, unknown>,
	allowed: readonly string[],
	filePath: string,
	field: string,
): void {
	for (const key of Object.keys(value)) {
		if (!allowed.includes(key))
			throw new ContextPolicyError("MW_CONTEXT_CONFIG_INVALID", filePath, `${field}.${key}`, "unknown field");
	}
}

function validateOverride(value: unknown, filePath: string, field: string): void {
	const entry = object(value, filePath, field);
	knownFields(entry, ["maxTokens", "compaction"], filePath, field);
	if (Object.hasOwn(entry, "maxTokens")) validateValue("maxTokens", entry.maxTokens, filePath, `${field}.maxTokens`);
	if (!Object.hasOwn(entry, "compaction")) return;
	const compaction = object(entry.compaction, filePath, `${field}.compaction`);
	knownFields(compaction, Object.keys(DEFAULTS.compaction), filePath, `${field}.compaction`);
	for (const [key, setting] of Object.entries(compaction))
		validateValue(`compaction.${key}` as ContextPolicyField, setting, filePath, `${field}.compaction.${key}`);
}

function validateValue(field: ContextPolicyField, value: unknown, filePath: string, location: string): void {
	let valid: boolean;
	if (field === "compaction.enabled") valid = typeof value === "boolean";
	else if (field === "compaction.targetRatio" || field === "compaction.triggerRatio")
		valid = typeof value === "number" && Number.isFinite(value) && value > 0 && value < 1;
	else valid = typeof value === "number" && Number.isSafeInteger(value) && value > 0;
	if (!valid) throw new ContextPolicyError("MW_CONTEXT_CONFIG_INVALID", filePath, location, "invalid policy value");
}

/** Missing files alone use defaults. Malformed or inaccessible files always fail closed. */
export function readContextPolicyDocument(filePath: string): ContextPolicyDocument | undefined {
	let text: string;
	try {
		text = fs.readFileSync(filePath, "utf8");
	} catch (error) {
		if (error instanceof Error && "code" in error && error.code === "ENOENT") return undefined;
		throw new ContextPolicyError("MW_CONTEXT_CONFIG_READ", filePath, "$", "cannot read configuration");
	}
	let value: unknown;
	try {
		value = JSON.parse(text.startsWith("\uFEFF") ? text.slice(1) : text);
	} catch {
		throw new ContextPolicyError("MW_CONTEXT_CONFIG_INVALID", filePath, "$", "invalid JSON");
	}
	const document = object(value, filePath, "$");
	knownFields(document, ["version", "defaults", "types"], filePath, "$");
	if (document.version !== 1)
		throw new ContextPolicyError("MW_CONTEXT_CONFIG_INVALID", filePath, "version", "expected version 1");
	if (Object.hasOwn(document, "defaults")) validateOverride(document.defaults, filePath, "defaults");
	if (Object.hasOwn(document, "types")) {
		for (const [type, entry] of Object.entries(object(document.types, filePath, "types"))) {
			if (!type.trim()) throw new ContextPolicyError("MW_CONTEXT_CONFIG_INVALID", filePath, "types", "empty type");
			validateOverride(entry, filePath, `types.${type}`);
		}
	}
	return document as unknown as ContextPolicyDocument;
}

function policyLocation(options: ContextPolicyLocation): {
	controlRoot: string;
	taskType: string;
	paths: ResolvedContextPolicy["paths"];
} {
	const controlRoot = path.resolve(options.taskFile ? controlRootFromTaskPath(options.taskFile) : options.controlRoot);
	let taskType = options.taskType;
	if (taskType === undefined && options.taskFile) {
		try {
			taskType = readTaskType(fs.readFileSync(options.taskFile, "utf8")).type ?? "default";
		} catch {
			throw new ContextPolicyError("MW_CONTEXT_CONFIG_READ", options.taskFile, "type", "cannot read task header");
		}
	}
	taskType ??= "pm";
	if (!taskType.trim())
		throw new ContextPolicyError("MW_CONTEXT_CONFIG_INVALID", controlRoot, "type", "empty task type");
	return {
		controlRoot,
		taskType,
		paths: {
			global: path.join(options.homeDir ?? os.homedir(), ".mw", "context.json"),
			project: path.join(controlRoot, ".mw", "context.json"),
		},
	};
}

function valueFor(entry: ContextPolicyOverride | undefined, field: ContextPolicyField): number | boolean | undefined {
	if (field === "maxTokens") return entry?.maxTokens;
	return entry?.compaction?.[field.slice("compaction.".length) as keyof ContextCompactionPolicy];
}

function resolveDocuments(
	location: ReturnType<typeof policyLocation>,
	global: ContextPolicyDocument | undefined,
	project: ContextPolicyDocument | undefined,
): ResolvedContextPolicy {
	const { controlRoot, taskType, paths } = location;
	const policy: ResolvedContextPolicy = {
		version: 1,
		controlRoot,
		taskType,
		paths,
		maxTokens: DEFAULTS.maxTokens,
		compaction: { ...DEFAULTS.compaction },
		sources: {} as Record<ContextPolicyField, ContextPolicySource>,
	};
	const effectiveGlobal = global ?? initialGlobalDocument();
	const layers: { entry: ContextPolicyOverride | undefined; source: ContextPolicySource }[] = [
		{
			entry: effectiveGlobal.defaults,
			source: { scope: "global", level: "defaults", path: paths.global, builtin: !global },
		},
		{
			entry: Object.hasOwn(effectiveGlobal.types ?? {}, taskType) ? effectiveGlobal.types?.[taskType] : undefined,
			source: { scope: "global", level: "type", path: paths.global, taskType, builtin: !global },
		},
		{
			entry: project?.defaults,
			source: { scope: "project", level: "defaults", path: paths.project, builtin: false },
		},
		{
			entry: Object.hasOwn(project?.types ?? {}, taskType) ? project?.types?.[taskType] : undefined,
			source: { scope: "project", level: "type", path: paths.project, taskType, builtin: false },
		},
	];
	for (const field of CONTEXT_POLICY_FIELDS) {
		let value = valueFor(DEFAULTS, field);
		let source: ContextPolicySource = { scope: "global", level: "defaults", path: paths.global, builtin: true };
		for (const layer of layers) {
			const setting = valueFor(layer.entry, field);
			if (setting !== undefined) {
				value = setting;
				source = layer.source;
			}
		}
		if (field === "maxTokens") policy.maxTokens = value as number;
		else Object.assign(policy.compaction, { [field.slice("compaction.".length)]: value });
		policy.sources[field] = { ...source };
	}
	return policy;
}

export function resolveContextPolicy(options: ContextPolicyLocation): ResolvedContextPolicy {
	const location = policyLocation(options);
	return resolveDocuments(
		location,
		readContextPolicyDocument(location.paths.global),
		readContextPolicyDocument(location.paths.project),
	);
}

export interface ContextPolicyUpdate extends ContextPolicyLocation {
	scope: ContextPolicyScope;
	type?: string;
	field: ContextPolicyField | "type";
	value?: number | boolean;
	operation: "set" | "clear";
}

/** A short same-directory lock and atomic replacement preserve unrelated explicit fields. */
export async function updateContextPolicy(options: ContextPolicyUpdate): Promise<ResolvedContextPolicy> {
	const location = policyLocation(options);
	const filePath = location.paths[options.scope];
	if (!filePath || !["set", "clear"].includes(options.operation))
		throw new ContextPolicyError(
			"MW_CONTEXT_CONFIG_INVALID",
			location.controlRoot,
			"$",
			"invalid update scope or operation",
		);
	if (options.type !== undefined && !options.type.trim())
		throw new ContextPolicyError("MW_CONTEXT_CONFIG_INVALID", filePath, "type", "empty type");
	if (options.field === "type") {
		if (options.operation !== "clear" || options.type === undefined)
			throw new ContextPolicyError("MW_CONTEXT_CONFIG_INVALID", filePath, "type", "clear type requires a type name");
	} else {
		if (!(CONTEXT_POLICY_FIELDS as readonly string[]).includes(options.field))
			throw new ContextPolicyError("MW_CONTEXT_CONFIG_INVALID", filePath, String(options.field), "unknown field");
		if (options.operation === "set") validateValue(options.field, options.value, filePath, options.field);
		if (options.operation === "set" && DELEGATED_CONTEXT_FIELDS.includes(options.field))
			throw new ContextPolicyError(
				"MW_CONTEXT_NATIVE_PARAMETER",
				filePath,
				options.field,
				"pi owns compaction generation parameters; configure pi compaction settings instead",
			);
	}
	let release: () => void;
	try {
		release = await acquireLock(`${filePath}.lock`, { retries: 0 });
	} catch {
		throw new ContextPolicyError("MW_CONTEXT_CONFIG_LOCK", filePath, "$", "configuration lock unavailable");
	}
	const temporary = path.join(path.dirname(filePath), `.context-${randomUUID()}.tmp`);
	try {
		const global = readContextPolicyDocument(location.paths.global);
		const project = readContextPolicyDocument(location.paths.project);
		const document =
			(options.scope === "global" ? global : project) ??
			(options.scope === "global" ? initialGlobalDocument() : { version: 1 });
		if (options.field === "type") {
			if (document.types && options.type !== undefined) delete document.types[options.type];
		} else {
			let entry: ContextPolicyOverride;
			if (options.type === undefined) entry = document.defaults ??= {};
			else {
				document.types ??= {};
				if (!Object.hasOwn(document.types, options.type))
					Object.defineProperty(document.types, options.type, {
						value: {},
						enumerable: true,
						configurable: true,
						writable: true,
					});
				entry = document.types[options.type];
			}
			if (options.field === "maxTokens") {
				if (options.operation === "clear") delete entry.maxTokens;
				else entry.maxTokens = options.value as number;
			} else {
				const key = options.field.slice("compaction.".length);
				entry.compaction ??= {};
				if (options.operation === "clear") Reflect.deleteProperty(entry.compaction, key);
				else Object.assign(entry.compaction, { [key]: options.value });
			}
		}
		const nextGlobal = options.scope === "global" ? document : global;
		const nextProject = options.scope === "project" ? document : project;
		// Resolve inherited active policy values for every affected type before writing.
		for (const taskType of new Set([
			location.taskType,
			options.type,
			...Object.keys(nextGlobal?.types ?? {}),
			...Object.keys(nextProject?.types ?? {}),
		])) {
			resolveDocuments({ ...location, taskType: taskType ?? "pm" }, nextGlobal, nextProject);
		}
		const resolved = resolveDocuments(location, nextGlobal, nextProject);
		fs.writeFileSync(temporary, `${JSON.stringify(document, null, 2)}\n`, {
			encoding: "utf8",
			flag: "wx",
			mode: 0o600,
		});
		fs.renameSync(temporary, filePath);
		return resolved;
	} catch (error) {
		if (error instanceof ContextPolicyError) throw error;
		throw new ContextPolicyError("MW_CONTEXT_CONFIG_WRITE", filePath, "$", "configuration update failed");
	} finally {
		try {
			fs.rmSync(temporary, { force: true });
		} finally {
			release();
		}
	}
}
