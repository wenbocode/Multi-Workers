import type { ExtensionAPI, ExtensionCommandContext } from "../../../core/extensions/types.ts";
import type { ModelRegistry } from "../../../core/model-registry.ts";
import { type MwContextPolicyDetails } from "./context-controller.ts";
export interface ContextExtensionOptions {
    controlRoot?: string;
    homeDir?: string;
    taskFile?: string;
}
/** Native core cancellation may never become an assistant message; preserve its signal identity. */
export declare function consumeNativeContextAbort(registry: ModelRegistry): boolean;
/** Native compaction may flatten provider diagnostics; retain the typed failure for worker settlement. */
export declare function consumeContextPolicyFailure(registry: ModelRegistry): MwContextPolicyDetails | undefined;
/** Install on PM and worker sessions, before the first provider request. */
export declare function registerContextPolicy(pi: ExtensionAPI, options?: ContextExtensionOptions): void;
export declare const CONTEXT_COMMAND_USAGE = "Usage: /mw context show [--type TYPE] [--json] | set <field> <value> --global|--project [--type TYPE] | clear <field|type> --global|--project [--type TYPE]";
/** User-command only: workers may inspect their policy, but cannot change it. */
export declare function runContextCommand(pi: ExtensionAPI, ctx: ExtensionCommandContext, controlRoot: string, args: string, options?: Omit<ContextExtensionOptions, "controlRoot">): Promise<void>;
//# sourceMappingURL=context-extension.d.ts.map