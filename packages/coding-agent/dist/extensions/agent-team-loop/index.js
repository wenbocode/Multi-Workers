import { pmActivate } from "./pm/pm-orchestrator.js";
import { registerProtectedConfigGuard } from "./shared/protected-config.js";
import { workerModeActivate } from "./worker/worker-mode.js";
// Defense against a double-load: if the same bundle is loaded twice in one host
// process (e.g. a global install AND a stale project-local copy), registering the
// tools twice makes the host reject the second load with a hard "tool conflicts"
// error and pi fails to start. A process-global guard makes the second activate()
// a no-op instead, so pi always comes up. mw init also removes redundant local
// copies (global-wins), but this keeps a rogue duplicate from ever crashing pi.
//
// The guard must only span ONE load pass: /new, /resume, /fork, and /reload all
// rebuild the runtime and re-run activate() with a fresh pi — a flag that never
// clears made those re-activations no-op, silently stripping every command,
// tool, handler, and the watch widget from the replaced session (a /pm-key
// switch then fell through to the LLM as an unknown command). Re-arming on
// session_shutdown keeps the double-load protection (both copies load within
// one pass, no shutdown in between) while letting replacements re-activate.
const ACTIVATION_FLAG = "__agentTeamLoopActivated";
export async function activate(pi) {
    const g = globalThis;
    // Registered before the guard check so even a blocked second copy re-arms
    // teardown (the delete is idempotent).
    pi.on("session_shutdown", () => {
        delete g[ACTIVATION_FLAG];
    });
    if (g[ACTIVATION_FLAG]) {
        return;
    }
    g[ACTIVATION_FLAG] = true;
    // Cross-window config guard (2026-09-15 incident: a session cleared
    // ~/.pi/agent/auth.json and every live window lost its credentials).
    // Registered in EVERY mode — PM, worker, and plain interactive windows —
    // after the double-load flag so a duplicate bundle copy cannot double-
    // register the listener. Hard block on write/edit/bash targeting the
    // protected agent config; reads pass through.
    registerProtectedConfigGuard(pi);
    if (process.env.PI_WORKER_TASK) {
        await workerModeActivate(pi);
    }
    else {
        pmActivate(pi);
    }
}
export default activate;
//# sourceMappingURL=index.js.map