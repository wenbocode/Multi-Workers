import * as fs from "node:fs";
import * as path from "node:path";
import { acquireLock } from "../shared/file-lock.ts";

export type Phase = "SPEC" | "DESIGN" | "PLAN" | "TASKS" | "EXECUTE" | "DONE";

const VALID_PHASES = new Set<Phase>(["SPEC", "DESIGN", "PLAN", "TASKS", "EXECUTE", "DONE"]);

export interface PmState {
	phase: Phase;
	claimId: string;
	taskKey: string;
	notes: string;
	updatedAt: string;
}

export class StateManager {
	private readonly statePath: string;

	constructor(agenticdocRoot: string, taskKey: string) {
		this.statePath = path.join(agenticdocRoot, taskKey, "pm-state.md");
	}

	read(): Partial<PmState> {
		if (!fs.existsSync(this.statePath)) return {};
		const content = fs.readFileSync(this.statePath, "utf8");
		const state: Partial<PmState> = {};
		for (const line of content.split("\n")) {
			const m = line.match(/^- Phase:\s*(.+)$/);
			if (m) state.phase = m[1].trim() as Phase;
			const m2 = line.match(/^- Claim-Id:\s*(.+)$/);
			if (m2) state.claimId = m2[1].trim();
		}
		return state;
	}

	async write(state: Partial<PmState>): Promise<void> {
		if (state.phase !== undefined && !VALID_PHASES.has(state.phase)) {
			throw new Error(`Invalid phase: ${state.phase}. Valid values: ${[...VALID_PHASES].join(", ")}`);
		}

		const current = this.read();
		const merged: PmState = {
			phase: (state.phase ?? current.phase ?? "SPEC") as Phase,
			claimId: state.claimId ?? current.claimId ?? "",
			taskKey: state.taskKey ?? current.taskKey ?? "",
			notes: state.notes ?? current.notes ?? "",
			updatedAt: new Date().toISOString(),
		};

		const content = [
			`# PM State: ${merged.taskKey}`,
			"",
			"## Section 1: Snapshot",
			`- Key: ${merged.taskKey}`,
			`- Claim-Id: ${merged.claimId}`,
			`- Phase: ${merged.phase}`,
			`- Updated: ${merged.updatedAt}`,
			"",
			"## Notes",
			"",
			merged.notes,
		].join("\n");

		const dir = path.dirname(this.statePath);
		fs.mkdirSync(dir, { recursive: true });
		const lockPath = `${this.statePath}.lock`;
		const release = await acquireLock(lockPath);
		try {
			const tmpPath = `${this.statePath}.tmp`;
			fs.writeFileSync(tmpPath, content, "utf8");
			fs.renameSync(tmpPath, this.statePath);
		} finally {
			release();
		}
	}
}
