import type { FileSystem } from "../types.ts";
import { Session } from "./session.ts";
import { type ForkOptions, type SessionCreateOptions, type SessionMetadata, type SessionRepo } from "./types.ts";
export type JsonlSessionRepoFileSystem = Pick<FileSystem, "cwd" | "absolutePath" | "joinPath" | "readTextFile" | "writeFile" | "appendFile" | "listDir" | "exists" | "createDir" | "remove">;
export interface JsonlSessionRepoOptions {
    fs: JsonlSessionRepoFileSystem;
    sessionsRoot: string;
    cwd?: string;
}
export interface JsonlSessionCreateOptions extends SessionCreateOptions {
    cwd?: string;
}
export interface JsonlSessionMetadata extends SessionMetadata {
    path: string;
    cwd: string;
}
export declare class JsonlSessionRepo implements SessionRepo<JsonlSessionMetadata, JsonlSessionCreateOptions>, AsyncDisposable {
    private readonly fs;
    private readonly sessionsRootInput;
    private readonly cwd;
    private readonly storages;
    private rootPromise;
    private tail;
    private disposed;
    constructor(options: JsonlSessionRepoOptions);
    create(options?: JsonlSessionCreateOptions): Promise<Session<JsonlSessionMetadata>>;
    open(metadata: JsonlSessionMetadata): Promise<Session<JsonlSessionMetadata>>;
    list(): Promise<JsonlSessionMetadata[]>;
    delete(metadata: JsonlSessionMetadata): Promise<void>;
    fork(source: JsonlSessionMetadata, options?: ForkOptions & JsonlSessionCreateOptions): Promise<Session<JsonlSessionMetadata>>;
    [Symbol.asyncDispose](): Promise<void>;
    private enqueue;
    private openDirect;
    private createDirect;
    private root;
    private pathForId;
}
//# sourceMappingURL=jsonl.d.ts.map