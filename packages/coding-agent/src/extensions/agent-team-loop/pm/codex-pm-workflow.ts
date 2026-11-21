import * as fs from "node:fs";
import * as path from "node:path";
import { type IndexStore, keyNameRefusal, normalizeKey } from "../shared/index-store.ts";
import type { WorkerDispatchAdapter } from "./ui-bridge.ts";

/** Only the Codex PM bridge installs this adapter. A task parameter or a
 * document marker alone never changes the ordinary MW dispatch checks. */
export function createCodexDispatchAdapter(
	agenticdocRoot: string,
	indexStore: IndexStore,
	expectedKey: string,
	expectedClaimId: string,
): WorkerDispatchAdapter {
	return (ownerKey) => {
		try {
			const nameRefusal = keyNameRefusal(ownerKey);
			if (nameRefusal) throw new Error(nameRefusal.message);
			if (expectedClaimId !== "codex" || normalizeKey(ownerKey) !== normalizeKey(expectedKey)) {
				throw new Error("Codex dispatch requires the bridge's explicit key and ClaimId codex");
			}
			const rows = indexStore.readAuthorityRows();
			const matches = rows.filter((row) => normalizeKey(row.key) === normalizeKey(ownerKey));
			if (matches.length !== 1) throw new Error("Expected one authoritative Codex key row");
			const row = matches[0];
			if (!row || row.status !== "active" || row.claimId !== "codex" || row.phase !== "EXECUTE") {
				throw new Error("Codex dispatch requires an active codex claim in EXECUTE");
			}
			const keyDir = path.join(fs.realpathSync.native(agenticdocRoot), row.key);
			const file = path.join(keyDir, "codex_doc.md");
			for (const candidate of [keyDir, file]) {
				const resolved = fs.realpathSync.native(candidate);
				const relative = path.relative(candidate, resolved);
				if (relative !== "") throw new Error("Linked Codex coordination paths are not supported");
			}
			const text = fs.readFileSync(file, "utf8").replace(/<!--[\s\S]*?-->/g, "");
			const fields: Record<string, string> = {};
			for (const label of ["Workflow", "Key", "Phase", "Claim-Id", "Status"]) {
				const values = [...text.matchAll(new RegExp(`^- ${label}:[ \\t]*([^\\r\\n]*)$`, "gm"))];
				if (values.length !== 1) throw new Error(`codex_doc.md must have exactly one '- ${label}:' line`);
				fields[label] = values[0]?.[1]?.trim() ?? "";
			}
			if (
				fields.Workflow !== "codex-lite" ||
				normalizeKey(fields.Key ?? "") !== normalizeKey(row.key) ||
				fields.Phase !== row.phase ||
				fields["Claim-Id"] !== row.claimId ||
				fields.Status !== row.status
			) {
				throw new Error("codex_doc.md workflow or state differs from the authoritative key row");
			}
			for (const heading of ["目标", "范围", "验收标准", "接续须知"]) {
				const sections = [
					...text.matchAll(
						new RegExp(`^##[ \\t]+${heading}[ \\t]*\\r?$([\\s\\S]*?)(?=^#{1,2}[ \\t]|$(?![\\s\\S]))`, "gm"),
					),
				];
				if (sections.length !== 1 || !(sections[0]?.[1] ?? "").trim()) {
					throw new Error(`codex_doc.md requires one nonempty '## ${heading}' section`);
				}
				if (heading === "验收标准") {
					const criteria = [...(sections[0]?.[1] ?? "").matchAll(/^- (AC-\d{3}):[ \t]*\S.*$/gm)];
					if (criteria.length === 0) {
						throw new Error("codex_doc.md 验收标准 requires a numbered '- AC-NNN:' criterion");
					}
					if (new Set(criteria.map((criterion) => criterion[1])).size !== criteria.length) {
						throw new Error("Duplicate acceptance criterion in codex_doc.md");
					}
				}
			}
			return { ok: true, phase: row.phase };
		} catch (error) {
			return {
				ok: false,
				reason: `Codex lightweight dispatch refused: ${error instanceof Error ? error.message : "unreadable key state"}`,
			};
		}
	};
}
