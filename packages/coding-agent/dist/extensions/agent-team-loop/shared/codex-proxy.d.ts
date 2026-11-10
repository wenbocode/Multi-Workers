export declare const LOCAL_CODEX_PROVIDER = "openai-codex-local";
export interface ProxyConfig {
    url: string;
    token: string;
}
export interface ProxyStatus {
    status: string;
    backend?: string;
    protocol?: number;
    pid?: number;
    concurrency?: number;
    timeout_s?: number;
    active?: {
        id: string;
        model: string;
        age_s: number;
        caller?: string;
    }[];
    last_success?: {
        at: number;
        model: string;
        duration_s: number;
    } | null;
    last_error?: {
        at: number;
        error: string;
    } | null;
    login?: string;
    model_check?: string;
    error?: string;
    checkedAt?: number;
    request?: {
        startedAt: number;
        heartbeatAt: number;
        phase: string;
        deadline: number;
    };
}
export declare function proxyProject(cwd?: string): string;
export declare function relayUrl(value: string): string;
export declare function readProxyConfig(project: string): ProxyConfig | undefined;
export declare function proxySnapshot(project: string): ProxyStatus | undefined;
export declare function setProxySnapshot(project: string, status: ProxyStatus): void;
export declare function checkProxy(config: ProxyConfig, options?: {
    fetch?: typeof fetch;
    signal?: AbortSignal;
    login?: boolean;
}): Promise<ProxyStatus>;
export declare function refreshProxy(project: string, login?: boolean): Promise<ProxyStatus>;
export declare function formatProxyStatus(status: ProxyStatus | undefined, now?: number): string[];
/** Arguments are a closed set; no shell or user-supplied executable. */
export declare function manageProxy(project: string, action: string, model?: string, deep?: boolean): Promise<ProxyStatus>;
//# sourceMappingURL=codex-proxy.d.ts.map