/**
 * cli-bridge.ts — skill-form transport: spawn the rag CLI, never through a shell (mw-rag-integration T-03).
 *
 * Contract (design §4.2): `<python> <cli_entry> <tool> --arg k=v ...`, stdout is
 * one JSON document, exit code 0 = success / 2 = connect or usage / 3 = tool
 * error. Arguments are passed as an argv array so paths and values containing
 * spaces, `&`, quotes or Unicode cannot be re-tokenized (P-004).
 *
 * The interpreter is resolved like the rest of the framework's Python bridges
 * (`shared/mw-runner.ts::PYTHON_EXE`: `python` on Windows, `python3` elsewhere),
 * with `MW_RAG_PYTHON` as an explicit override for tests and non-standard
 * installs. It must NOT be `process.execPath` (that is the Node/Bun binary; the
 * cli_entry is a Python script per the skill contract).
 */
export interface CliEntryPoint {
    dir: string;
    cliEntry: string;
    timeoutMs: number;
}
export interface CallCliOptions {
    signal: AbortSignal;
    env: NodeJS.ProcessEnv;
    onUpdate?: (message: string) => void;
}
export declare function resolveRagPython(env?: NodeJS.ProcessEnv): string;
export declare function callCli(cliEntry: CliEntryPoint, name: string, args: Record<string, unknown>, opts: CallCliOptions): Promise<unknown>;
//# sourceMappingURL=cli-bridge.d.ts.map