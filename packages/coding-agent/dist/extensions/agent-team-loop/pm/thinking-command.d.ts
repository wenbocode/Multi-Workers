import type { ExtensionCommandContext } from "../../../core/extensions/types.ts";
import { type MwCliResult } from "../shared/mw-runner.ts";
/**
 * `/mw thinking ...` — strict, thin window face over `mw.py thinking`.
 *
 * Python is the single source of YAML semantics; this module NEVER edits the
 * config, never re-implements role/level rules beyond the closed validation
 * needed to reject illegal input before a subprocess starts, and forwards an
 * argv array (never a shell string) through `thinkingMw`. The runner is
 * injectable so the real registered `/mw` handler can be driven offline.
 *
 * Accepted shapes (bare `thinking` == `show`):
 *   /mw thinking [show]
 *   /mw thinking set   <default|role> <level>
 *   /mw thinking clear <default|role|all>
 */
/** Worker roles the thinking config accepts. `main` (the PM/model role) and any
 * role alias are deliberately excluded — thinking never targets `main`. */
export declare const THINKING_ROLES: readonly ["coding", "review", "research", "vision", "decide_prepare"];
/** Closed level set. Kept here only as a pre-spawn guard; Python owns the real
 * validation/serialization (including keeping `off` a string). */
export declare const THINKING_LEVELS: readonly ["off", "minimal", "low", "medium", "high", "xhigh", "max"];
export declare const THINKING_USAGE: string;
export declare function runMwThinkingCommand(ctx: ExtensionCommandContext, projectDir: string, argsText: string, runner?: (projectDir: string, args: string[]) => MwCliResult): Promise<void>;
//# sourceMappingURL=thinking-command.d.ts.map