import { type Api, type AssistantMessageEventStream, type Model } from "@earendil-works/pi-ai";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "../../../core/extensions/types.ts";
export declare function limitProviderStream(model: Model<Api>, start: () => AssistantMessageEventStream, signal: AbortSignal | undefined, directory: string, onWait?: () => void, onReady?: () => void): AssistantMessageEventStream;
/** Register native wrappers so model refresh continues to delegate through the limiter. */
export declare function installConcurrencyProviders(ctx: ExtensionContext): void;
export declare function registerModelConcurrency(pi: ExtensionAPI): void;
export declare function runConcurrencyCommand(pi: ExtensionAPI, ctx: ExtensionCommandContext, args: string): Promise<void>;
//# sourceMappingURL=model-concurrency-extension.d.ts.map