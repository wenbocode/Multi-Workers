import * as fs from "node:fs";
import * as path from "node:path";
import { goalPath } from "../shared/paths.js";
export function goalMtime(agenticdocRoot) {
    const goalPathResolved = goalPath(agenticdocRoot);
    try {
        return fs.statSync(goalPathResolved).mtimeMs;
    }
    catch {
        return 0;
    }
}
export function writePhaseFile(taskKey, agenticdocRoot, phaseIndex, summary) {
    const progressDir = path.join(agenticdocRoot, taskKey, "progress");
    fs.mkdirSync(progressDir, { recursive: true });
    const content = `# Phase ${phaseIndex + 1}\n\n${summary || "(phase complete)"}\n`;
    fs.writeFileSync(path.join(progressDir, `phase-${phaseIndex + 1}.md`), content, "utf8");
}
//# sourceMappingURL=phase-runner.js.map