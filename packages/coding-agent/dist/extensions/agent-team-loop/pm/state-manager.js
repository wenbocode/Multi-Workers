import * as fs from "node:fs";
import * as path from "node:path";
import { acquireLock } from "../shared/file-lock.js";
const VALID_PHASES = new Set(["SPEC", "DESIGN", "PLAN", "TASKS", "EXECUTE", "DONE"]);
export class StateManager {
    statePath;
    constructor(agenticdocRoot, taskKey) {
        this.statePath = path.join(agenticdocRoot, taskKey, "pm-state.md");
    }
    read() {
        if (!fs.existsSync(this.statePath))
            return {};
        const content = fs.readFileSync(this.statePath, "utf8");
        const state = {};
        for (const line of content.split("\n")) {
            const m = line.match(/^- Phase:\s*(.+)$/);
            if (m)
                state.phase = m[1].trim();
            const m2 = line.match(/^- Claim-Id:\s*(.+)$/);
            if (m2)
                state.claimId = m2[1].trim();
        }
        return state;
    }
    async write(state) {
        if (state.phase !== undefined && !VALID_PHASES.has(state.phase)) {
            throw new Error(`Invalid phase: ${state.phase}. Valid values: ${[...VALID_PHASES].join(", ")}`);
        }
        const current = this.read();
        const merged = {
            phase: (state.phase ?? current.phase ?? "SPEC"),
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
        }
        finally {
            release();
        }
    }
}
//# sourceMappingURL=state-manager.js.map