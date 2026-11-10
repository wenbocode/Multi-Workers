import { type Api, type Context, type Model, type SimpleStreamOptions } from "@earendil-works/pi-ai";
import type { ExtensionAPI, ExtensionCommandContext } from "../../../core/extensions/types.ts";
export declare const PROXY_HEARTBEAT_TIMEOUT_MS = 10000;
/** Shared by request serialization and the conservative request-budget estimator. */
export declare function createLocalCodexPayload(model: Model<Api>, context: Context, options?: SimpleStreamOptions, project?: string): {
    model: string;
    context: Context;
    reasoning: import("@earendil-works/pi-ai").ThinkingLevel | undefined;
    caller?: string | undefined;
};
export declare function streamLocalCodex(model: Model<Api>, context: Context, options?: SimpleStreamOptions, project?: string): import("@earendil-works/pi-ai").AssistantMessageEventStream;
export declare function registerLocalCodex(pi: ExtensionAPI): void;
export declare function configureLocalCodex(pi: ExtensionAPI, project: string): boolean;
export declare function runProxyCommand(pi: ExtensionAPI, ctx: ExtensionCommandContext, project: string, args: string): Promise<void>;
export default registerLocalCodex;
//# sourceMappingURL=codex-local.d.ts.map