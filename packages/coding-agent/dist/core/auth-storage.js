/**
 * CredentialStore implementation backed by auth.json.
 * Provider auth orchestration belongs to ModelRuntime and pi-ai Models.
 */
import { chmodSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import { dirname, join } from "path";
import lockfile from "proper-lockfile";
import { setTimeout as sleep } from "timers/promises";
import { getAgentDir } from "../config.js";
import { raceWithAbortSignal } from "../utils/abort.js";
import { getFileRevision, normalizePath } from "../utils/paths.js";
import { resolveConfigValue } from "./resolve-config-value.js";
const AUTH_FILE_WRITE_OPTIONS = { encoding: "utf-8", mode: 0o600 };
let sharedAuthFileReadState;
export class FileAuthStorageBackend {
    authPath;
    constructor(authPath = join(getAgentDir(), "auth.json")) {
        this.authPath = normalizePath(authPath);
    }
    ensureParentDir() {
        const dir = dirname(this.authPath);
        if (!existsSync(dir)) {
            mkdirSync(dir, { recursive: true, mode: 0o700 });
        }
    }
    ensureFileExists() {
        if (!existsSync(this.authPath)) {
            writeFileSync(this.authPath, "{}", AUTH_FILE_WRITE_OPTIONS);
            chmodSync(this.authPath, 0o600);
        }
    }
    acquireLockSyncWithRetry(path) {
        const maxAttempts = 10;
        const delayMs = 20;
        let lastError;
        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                return lockfile.lockSync(path, { realpath: false });
            }
            catch (error) {
                const code = typeof error === "object" && error !== null && "code" in error
                    ? String(error.code)
                    : undefined;
                if (code !== "ELOCKED" || attempt === maxAttempts) {
                    throw error;
                }
                lastError = error;
                const start = Date.now();
                while (Date.now() - start < delayMs) {
                    // Sleep synchronously to avoid changing callers to async.
                }
            }
        }
        throw lastError ?? new Error("Failed to acquire auth storage lock");
    }
    withLock(fn) {
        this.ensureParentDir();
        this.ensureFileExists();
        let release;
        try {
            release = this.acquireLockSyncWithRetry(this.authPath);
            const current = existsSync(this.authPath) ? readFileSync(this.authPath, "utf-8") : undefined;
            const { result, next } = fn(current);
            if (next !== undefined) {
                writeFileSync(this.authPath, next, AUTH_FILE_WRITE_OPTIONS);
                chmodSync(this.authPath, 0o600);
            }
            return result;
        }
        finally {
            if (release) {
                release();
            }
        }
    }
    async acquireLockAsync(signal, onCompromised) {
        const maxRetries = 10;
        for (let attempt = 0; attempt <= maxRetries; attempt++) {
            signal?.throwIfAborted();
            let release;
            try {
                release = await lockfile.lock(this.authPath, {
                    realpath: false,
                    retries: 0,
                    stale: 30000,
                    onCompromised,
                });
            }
            catch (error) {
                signal?.throwIfAborted();
                const code = typeof error === "object" && error !== null && "code" in error
                    ? String(error.code)
                    : undefined;
                if (code !== "ELOCKED" || attempt === maxRetries)
                    throw error;
                const delayMs = Math.min(Math.round((Math.random() + 1) * 100 * 2 ** attempt), 10000);
                if (signal)
                    await sleep(delayMs, undefined, { signal });
                else
                    await sleep(delayMs);
                continue;
            }
            if (signal?.aborted) {
                await release();
                signal.throwIfAborted();
            }
            return release;
        }
        throw new Error("Failed to acquire auth storage lock");
    }
    async withLockAsync(fn, options) {
        options?.signal?.throwIfAborted();
        this.ensureParentDir();
        this.ensureFileExists();
        let release;
        let lockCompromised = false;
        let lockCompromisedError;
        const throwIfCompromised = () => {
            if (lockCompromised) {
                throw lockCompromisedError ?? new Error("Auth storage lock was compromised");
            }
        };
        try {
            release = await this.acquireLockAsync(options?.signal, (error) => {
                lockCompromised = true;
                lockCompromisedError = error;
            });
            throwIfCompromised();
            options?.signal?.throwIfAborted();
            const current = existsSync(this.authPath) ? readFileSync(this.authPath, "utf-8") : undefined;
            const { result, next } = await fn(current);
            throwIfCompromised();
            options?.signal?.throwIfAborted();
            if (next !== undefined) {
                writeFileSync(this.authPath, next, AUTH_FILE_WRITE_OPTIONS);
                chmodSync(this.authPath, 0o600);
            }
            throwIfCompromised();
            return result;
        }
        finally {
            if (release) {
                try {
                    await release();
                }
                catch {
                    // Ignore unlock errors when lock is compromised.
                }
            }
        }
    }
}
export class InMemoryAuthStorageBackend {
    value;
    asyncChain = Promise.resolve();
    withLock(fn) {
        const { result, next } = fn(this.value);
        if (next !== undefined) {
            this.value = next;
        }
        return result;
    }
    withLockAsync(fn, options) {
        const previous = this.asyncChain;
        const operation = (async () => {
            await previous.catch(() => { });
            options?.signal?.throwIfAborted();
            const { result, next } = await fn(this.value);
            options?.signal?.throwIfAborted();
            if (next !== undefined) {
                this.value = next;
            }
            return result;
        })();
        this.asyncChain = operation.catch(() => { });
        return raceWithAbortSignal(operation, options?.signal);
    }
}
/**
 * Credential storage backed by a JSON file.
 */
export class AuthStorage {
    storage;
    authPath;
    readState;
    constructor(storage, authPath) {
        this.storage = storage;
        this.readState = { data: {} };
        if (authPath && !sharedAuthFileReadState) {
            this.authPath = authPath;
            sharedAuthFileReadState = { authPath, readState: this.readState };
        }
        else if (authPath && sharedAuthFileReadState?.authPath === authPath) {
            this.authPath = authPath;
            this.readState = sharedAuthFileReadState.readState;
        }
        if (this.authPath) {
            const revision = getFileRevision(this.authPath);
            if (revision !== undefined && revision === this.readState.revision)
                return;
        }
        this.reload();
    }
    static create(authPath = join(getAgentDir(), "auth.json")) {
        const normalizedAuthPath = normalizePath(authPath);
        return new AuthStorage(new FileAuthStorageBackend(normalizedAuthPath), normalizedAuthPath);
    }
    static fromStorage(storage) {
        return new AuthStorage(storage);
    }
    static inMemory(data = {}) {
        const storage = new InMemoryAuthStorageBackend();
        storage.withLock(() => ({ result: undefined, next: JSON.stringify(data, null, 2) }));
        return AuthStorage.fromStorage(storage);
    }
    parseStorageData(content) {
        if (!content) {
            return {};
        }
        return JSON.parse(content);
    }
    updateReadState(data, revision) {
        this.readState.data = data;
        this.readState.revision = revision;
    }
    /**
     * Reload credentials from storage.
     */
    reload() {
        let content;
        let revision;
        try {
            this.storage.withLock((current) => {
                content = current;
                revision = this.authPath ? getFileRevision(this.authPath) : undefined;
                return { result: undefined };
            });
            this.updateReadState(this.parseStorageData(content), revision);
        }
        catch {
            // Preserve the last valid in-memory snapshot.
        }
    }
    async reloadFromStorageAsync(options) {
        return this.storage.withLockAsync(async (content) => {
            const currentData = this.parseStorageData(content);
            const revision = this.authPath ? getFileRevision(this.authPath) : undefined;
            this.updateReadState(currentData, revision);
            return { result: currentData };
        }, options);
    }
    readLatestData(options) {
        options?.signal?.throwIfAborted();
        if (!this.authPath) {
            const reload = this.reloadFromStorageAsync(options);
            return options?.signal ? reload : reload.catch(() => this.readState.data);
        }
        const revision = getFileRevision(this.authPath);
        if (revision !== undefined && revision === this.readState.revision) {
            return Promise.resolve(this.readState.data);
        }
        if (options?.signal)
            return this.reloadFromStorageAsync(options);
        if (!this.readState.reload) {
            const reload = this.reloadFromStorageAsync().catch(() => this.readState.data);
            this.readState.reload = reload;
            void reload.then(() => {
                if (this.readState.reload === reload)
                    this.readState.reload = undefined;
            });
        }
        return this.readState.reload;
    }
    async read(provider, options) {
        const credential = (await this.readLatestData(options))[provider];
        options?.signal?.throwIfAborted();
        if (credential?.type !== "api_key")
            return credential;
        if (credential.key === undefined)
            return credential;
        return { ...credential, key: resolveConfigValue(credential.key, credential.env) };
    }
    async modify(provider, fn, options) {
        let latestData = this.readState.data;
        let revision;
        const result = await this.storage.withLockAsync(async (content) => {
            const currentData = this.parseStorageData(content);
            const next = await fn(currentData[provider]);
            if (next === undefined) {
                latestData = currentData;
                revision = this.authPath ? getFileRevision(this.authPath) : undefined;
                return { result: currentData[provider] };
            }
            const merged = { ...currentData, [provider]: next };
            latestData = merged;
            return { result: next, next: JSON.stringify(merged, null, 2) };
        }, options);
        this.updateReadState(latestData, revision);
        return result;
    }
    async delete(provider, options) {
        let latestData = this.readState.data;
        await this.storage.withLockAsync(async (content) => {
            const currentData = this.parseStorageData(content);
            delete currentData[provider];
            latestData = currentData;
            return { result: undefined, next: JSON.stringify(currentData, null, 2) };
        }, options);
        this.updateReadState(latestData);
    }
    /** List credential metadata without resolving configured key values. */
    async list(options) {
        const entries = Object.entries(await this.readLatestData(options));
        options?.signal?.throwIfAborted();
        return entries.map(([providerId, credential]) => ({ providerId, type: credential.type }));
    }
}
/**
 * One-off synchronous read of a stored credential from an auth.json file,
 * without instantiating a store or resolving configured key values.
 */
export function readStoredCredential(providerId, authPath = join(getAgentDir(), "auth.json")) {
    try {
        const data = JSON.parse(readFileSync(normalizePath(authPath), "utf-8"));
        return data[providerId];
    }
    catch {
        return undefined;
    }
}
//# sourceMappingURL=auth-storage.js.map