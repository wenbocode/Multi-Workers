import { initiatorRoleFromWorkerTask, registerAskDecisionTool } from "./pm/decision-tool.js";
import { pmActivate } from "./pm/pm-orchestrator.js";
import { registerImplementationGate } from "./shared/implementation-gate.js";
import { registerProtectedConfigGuard } from "./shared/protected-config.js";
import { registerWorktreeJunctionGuard } from "./shared/worktree-junction-guard.js";
import { registerDecisionSignoffGuard, registerXkeyGateGuard } from "./shared/xkey-gate-guard.js";
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
    // XKEY gate-dir guard (xkey-repair-mechanism D-008, AC-004): gate files
    // (.agenticdoc/_autopilot/gates/**) are the human-answer channel, so the
    // agent tool layer is refused (write/edit/bash, fail-closed) while reads
    // and the xkey proposal tree stay open. Registered in EVERY mode, same
    // position as the protected-config guard so a worker window is covered.
    registerXkeyGateGuard(pi);
    // Decision sign-off guard (mw-decision-substitution D-015, AC-009/AC-010):
    // `evidence/review/sign-final.md` is the human answer channel and
    // `.mw/decide-points.json` is the only authority source (machines never
    // write it), so the agent tool layer is refused there (write/edit/bash,
    // fail-closed) while reads and `decision-review-*.md` stay open. Same
    // mechanism as the xkey guard above, registered right after it in EVERY
    // mode so a worker window is covered too.
    registerDecisionSignoffGuard(pi);
    // Implementation entry gate (mw-implementation-gate): write/edit/bash
    // calls targeting code paths under packages/ pass only with an active
    // AgenticTask key claim for this window, a dispatched worker env
    // (PI_WORKER_TASK), or a fresh (<=24h) mini-spec fast path; otherwise the
    // call is blocked with key-creation guidance. Every block and mini-pass
    // is audited to .agenticdoc/_impl_gate.log (best-effort). Registered in
    // EVERY mode, same position as the protected-config guard: after the
    // double-load flag, before the PM/Worker mode branches.
    registerImplementationGate(pi);
    // Worktree junction guard (mw-worktree-junction-guard G1, AC-001/002/003):
    // `git worktree remove --force <path>` walks THROUGH reparse points and
    // deletes the link target (the 2026-10-09 incident removed 3,456 tracked
    // files from the shared tree). The guard resolves the operand, scans the
    // target tree, and blocks when it cannot prove the tree is free of reparse
    // points, pointing at the `mw worktree rm <path>` replacement command.
    // Registered in EVERY mode, same position as the other guards: after the
    // double-load flag, before the PM/Worker mode branches.
    registerWorktreeJunctionGuard(pi);
    if (process.env.PI_WORKER_TASK) {
        await workerModeActivate(pi);
        // `ask_decision` + `decision_receipt` (mw-decision-substitution T-05, design
        // D-017/Q1 §1.3; mw-decision-context T04): ONE shared material entry for
        // both asking roles. Registered AFTER workerModeActivate so this module's
        // `before_agent_start` handler runs after the role's active-set
        // recomputation and can append the tools for every role without editing
        // TOOL_ALLOWLISTS (T-17 parity lock). The initiator role is the worker's
        // own card type — a worker can never claim to be the PM and therefore can
        // never reach dp2/dp25 (AC-006/AC-010).
        registerAskDecisionTool(pi, {
            initiatorRole: initiatorRoleFromWorkerTask(process.env.PI_WORKER_TASK),
        });
    }
    else {
        pmActivate(pi);
        // PM branch: the SAME entry, with the structural `pm` role. The PM is the
        // only initiator of dp2 (主动 checkpoint) and of the dp25 sign-off material
        // (design D003/§4.4); a worker window is refused with zero spawn. The PM
        // passes its own `key` (and a `task_key` only when the decision is about a
        // real task) — this call site never guesses either.
        registerAskDecisionTool(pi, { initiatorRole: "pm" });
    }
}
export default activate;
//# sourceMappingURL=index.js.map