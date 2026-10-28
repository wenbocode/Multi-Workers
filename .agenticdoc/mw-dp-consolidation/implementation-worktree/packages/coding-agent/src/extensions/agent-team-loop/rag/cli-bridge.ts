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

import { spawn } from "node:child_process";
import { type RagErrorKind, RagToolError } from "./mcp-client.ts";

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

const SECRET_ENV_KEY_RE = /(token|secret|password|passwd|api[_-]?key|credential)/i;

export function resolveRagPython(env: NodeJS.ProcessEnv = process.env): string {
	const override = env.MW_RAG_PYTHON?.trim();
	if (override !== undefined && override.length > 0) return override;
	return process.platform === "win32" ? "python" : "python3";
}

export async function callCli(
	cliEntry: CliEntryPoint,
	name: string,
	args: Record<string, unknown>,
	opts: CallCliOptions,
): Promise<unknown> {
	const argv = [cliEntry.cliEntry, name];
	for (const [key, value] of Object.entries(args)) {
		if (value === undefined || value === null) continue;
		argv.push("--arg", `${key}=${serializeArg(value)}`);
	}

	const interpreter = resolveRagPython(opts.env);
	const server = cliEntry.cliEntry;

	if (opts.signal.aborted) throw cliError("timeout", server, name, "call cancelled before spawn");

	return await new Promise<unknown>((resolve, reject) => {
		const child = spawn(interpreter, argv, {
			cwd: cliEntry.dir,
			env: opts.env,
			shell: false,
			windowsHide: true,
		});

		const stdoutChunks: Buffer[] = [];
		const stderrChunks: Buffer[] = [];
		let timedOut = false;
		let settled = false;

		const timeoutMs = cliEntry.timeoutMs;
		const timer =
			Number.isFinite(timeoutMs) && timeoutMs > 0
				? setTimeout(() => {
						timedOut = true;
						child.kill();
					}, timeoutMs)
				: undefined;

		const onAbort = (): void => {
			child.kill();
		};
		opts.signal.addEventListener("abort", onAbort, { once: true });

		const cleanup = (): void => {
			if (timer !== undefined) clearTimeout(timer);
			opts.signal.removeEventListener("abort", onAbort);
		};

		child.stdout.on("data", (chunk: Buffer) => stdoutChunks.push(chunk));
		child.stderr.on("data", (chunk: Buffer) => stderrChunks.push(chunk));
		child.stdin.end();

		child.on("error", (error) => {
			if (settled) return;
			settled = true;
			cleanup();
			reject(
				cliError("connect", server, name, `failed to start ${interpreter}: ${error.message}`, {
					code: (error as NodeJS.ErrnoException).code,
				}),
			);
		});

		child.on("close", (code) => {
			if (settled) return;
			settled = true;
			cleanup();

			const rawStderr = Buffer.concat(stderrChunks).toString("utf8");
			const stderr = redactEnvSecrets(rawStderr, opts.env);
			const detail = {
				exitCode: code,
				stderr: stderr.length > 0 ? truncate(stderr) : undefined,
			};

			if (timedOut || (code === null && opts.signal.aborted)) {
				reject(cliError("timeout", server, name, `cli call timed out after ${timeoutMs}ms`, detail));
				return;
			}
			if (code === 0) {
				const text = Buffer.concat(stdoutChunks).toString("utf8").trim();
				if (text.length === 0) {
					reject(cliError("protocol", server, name, "cli produced no stdout JSON", detail));
					return;
				}
				try {
					resolve(JSON.parse(text));
				} catch {
					reject(cliError("protocol", server, name, "cli stdout is not valid JSON", detail));
				}
				return;
			}
			if (code === 2) {
				reject(cliError("connect", server, name, "cli reported a connection or usage failure", detail));
				return;
			}
			if (code === 3) {
				reject(cliError("tool", server, name, "cli reported a tool-level error", detail));
				return;
			}
			reject(cliError("protocol", server, name, `cli exited with unexpected code ${String(code)}`, detail));
		});
	});
}

function cliError(kind: RagErrorKind, server: string, tool: string, message: string, detail?: unknown): RagToolError {
	return new RagToolError({ kind, server, tool, message, detail });
}

function serializeArg(value: unknown): string {
	if (typeof value === "string") return value;
	if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint") return String(value);
	return JSON.stringify(value);
}

/** Best-effort redaction of token-like values from the inherited environment. */
function redactEnvSecrets(text: string, env: NodeJS.ProcessEnv): string {
	if (text.length === 0) return text;
	let redacted = text;
	for (const [key, value] of Object.entries(env)) {
		if (value === undefined || value.length < 4) continue;
		if (!SECRET_ENV_KEY_RE.test(key)) continue;
		redacted = redacted.split(value).join("<redacted>");
	}
	return redacted;
}

function truncate(text: string): string {
	return text.length > 1000 ? text.slice(0, 1000) : text;
}
