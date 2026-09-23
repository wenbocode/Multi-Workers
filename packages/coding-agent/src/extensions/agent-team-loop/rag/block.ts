/**
 * rag/block.ts — single source of the task.md `<!-- mw-rag: v1 -->` block
 * (mw-rag-integration D-009 / T-04).
 *
 * The render is a pure function of the merged `RagConfig` and the task
 * metadata; the Python side (`mw_common.render_rag_block`, T-06) emits the
 * byte-identical text. The byte contract is locked by
 * `packages/multi-workers/test/fixtures/rag-block.golden.md` (347 B, **no
 * trailing newline**); the injection side appends it with
 * `content.rstrip() + "\n\n" + block + "\n"`.
 *
 * `renderRagBlock` returns null when `enabled` is empty — the structural
 * zero-impact guarantee (D-014/AC-001): no RAG byte is written at all.
 */

import { roleForTaskType } from "../shared/dispatch-models.ts";
import {
	DEFAULT_RAG_CHAT_BUDGET,
	DEFAULT_RAG_TIME_BUDGET_S,
	type RagConfig,
	ragFingerprint,
	resolveDefaults,
} from "./config.ts";

/** Marker opening the block; the idempotent replacement boundary. */
export const RAG_MARKER_V1 = "<!-- mw-rag: v1 -->";

/** Citation grammar rendered into task.md (design D-004). */
export const RAG_CITATION_SYNTAX = "<server>:<source>:<file_path>:<line>";

/**
 * Task metadata the block depends on. Field names are the TS runtime
 * (camelCase) shape; the Python side reads its own `chat_budget` /
 * `time_budget_s` keys. Both drive the same rendered lines.
 */
export interface RagTaskMeta {
	type?: string;
	role?: string;
	phase?: string;
	chatBudget?: number;
	timeBudgetS?: number;
}

function positiveInt(value: unknown): number | null {
	if (typeof value === "number" && Number.isInteger(value) && value > 0) return value;
	return null;
}

/** task.md header > role spec > rag.budgets > built-in default (D-006). */
function resolveBudget(
	explicit: number | undefined,
	roleValue: number | undefined,
	globalValue: number | undefined,
	fallback: number,
): number {
	return positiveInt(explicit) ?? positiveInt(roleValue) ?? positiveInt(globalValue) ?? fallback;
}

/**
 * Render the `mw-rag: v1` block for one task, or null when the project has no
 * enabled servers. Mirrors `mw_common.render_rag_block` line for line.
 */
export function renderRagBlock(config: RagConfig, meta: RagTaskMeta): string | null {
	const enabled = config.enabled.filter((name) => typeof name === "string" && name.trim().length > 0);
	if (enabled.length === 0) return null;

	const type = meta.type ?? "";
	const role = meta.role ?? roleForTaskType(type);
	const phase = meta.phase ?? "";
	const roleSpec = config.roles[role];

	// One resolution source (D-102/D-104/D-109): the same `resolveDefaults`
	// that `callRag` uses, so the rendered `[mw] Rewrite:` line and the runtime
	// wire-tool choice cannot disagree.
	const { server, source, rewrite } = resolveDefaults(config, role, phase);

	const lines: string[] = [RAG_MARKER_V1, `[mw] RAG enabled: ${enabled.join(", ")}`];
	const requiredRoles = Object.entries(config.roles)
		.filter(([, spec]) => spec.require === true)
		.map(([name]) => name)
		.sort();
	if (requiredRoles.length > 0) lines.push(`[mw] Required roles: ${requiredRoles.join(", ")}`);
	const requiredPhases = Object.entries(config.phases)
		.filter(([, spec]) => spec.require === true)
		.map(([name]) => name)
		.sort();
	if (requiredPhases.length > 0) lines.push(`[mw] Required phases: ${requiredPhases.join(", ")}`);

	lines.push(`[mw] Default server: ${server ?? "none"}`);
	lines.push(`[mw] Default source: ${source ?? "none"}`);
	lines.push(`[mw] Rewrite: ${rewrite ? "true" : "false"}`);
	lines.push(
		`[mw] Chat budget: ${resolveBudget(meta.chatBudget, roleSpec?.chatBudget, config.budgets.chat, DEFAULT_RAG_CHAT_BUDGET)}`,
	);
	lines.push(
		`[mw] Time budget: ${resolveBudget(meta.timeBudgetS, roleSpec?.timeBudgetS, config.budgets.timeS, DEFAULT_RAG_TIME_BUDGET_S)}s`,
	);
	lines.push(`[mw] Citation syntax: ${RAG_CITATION_SYNTAX}`);
	lines.push(`fingerprint=${config.fingerprint.length > 0 ? config.fingerprint : ragFingerprint(config, enabled)}`);
	return lines.join("\n");
}
