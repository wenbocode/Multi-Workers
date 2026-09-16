export interface LockOptions {
    retries?: number;
    baseDelayMs?: number;
}
export declare function acquireLock(lockPath: string, opts?: LockOptions): Promise<() => void>;
//# sourceMappingURL=file-lock.d.ts.map