import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { createServer } from "node:net";
import { findMwPy, PYTHON_EXE } from "../shared/mw-runner.ts";

/** Keep sign-off attestation in the owning PM's process. Only the direct CLI
 * child receives the write challenge. Readers can recheck the same proof
 * without gaining the write challenge or any authority to execute an action. */
export async function runOfflineSignoff(
	projectDir: string,
	key: string,
	readProof: () => Record<string, unknown> | undefined,
	signal?: AbortSignal,
): Promise<Record<string, unknown>> {
	const unavailable = { signoff_status: "failed", decision_source: "pm-evidence" };
	const mw = findMwPy();
	if (process.platform !== "win32" || !mw || signal?.aborted) return unavailable;
	const id = randomBytes(16).toString("hex");
	const nonce = randomBytes(16).toString("hex");
	let writeAllowed = true;
	let prepared: string | undefined;
	let publication: string | undefined;
	const server = createServer((socket) => {
		let input = "";
		socket.setTimeout(2_000, () => socket.destroy());
		socket.on("error", () => socket.destroy());
		socket.on("data", (bytes: Buffer) => {
			input += bytes.toString("ascii");
			if (input.length > 128) {
				socket.destroy();
				return;
			}
			if (!input.endsWith("\n")) return;
			try {
				let proof: Record<string, unknown> | undefined;
				const request = /^(prepare|publish):([a-f0-9]{32}):([a-f0-9]{64})\n$/.exec(input);
				if (writeAllowed && request?.[2] === nonce) {
					const current = readProof();
					const snapshot = request[3];
					if (current && request[1] === "prepare" && (prepared === undefined || prepared === snapshot)) {
						prepared = snapshot;
						proof = { ...current, prepared_sha256: prepared };
					} else if (current && request[1] === "publish" && prepared === snapshot) {
						publication = snapshot;
						proof = { ...current, publication_sha256: publication };
					}
				} else if (input === "read\n" && publication !== undefined) {
					const current = readProof();
					if (current) proof = { ...current, publication_sha256: publication };
				} else if (writeAllowed && input === `write:${nonce}\n`) {
					const current = readProof();
					if (current) proof = { ...current, prepared_sha256: prepared };
				}
				const body = JSON.stringify(proof ?? null);
				socket.end(Buffer.byteLength(body) < 65_000 ? `${body}\n` : "null\n");
			} catch {
				socket.end("null\n");
			}
		});
	});
	const address = `\\\\.\\pipe\\mw-local-sign-${process.pid}-${id}`;
	try {
		await new Promise<void>((resolve, reject) => {
			server.once("error", reject);
			server.listen(address, resolve);
		});
		server.unref();
		const run = (reconcile: boolean) =>
			new Promise<Record<string, unknown>>((resolve) => {
				const child = spawn(PYTHON_EXE, [mw, "decide", "sign", key, "--project", projectDir, "--stdin", "--json"], {
					windowsHide: true,
					stdio: ["pipe", "pipe", "ignore"],
					signal: reconcile ? undefined : signal,
				});
				let stdout = "";
				const deadline = setTimeout(() => child.kill(), reconcile ? 5_000 : 10_000);
				child.stdin.on("error", () => {});
				child.on("error", () => {
					clearTimeout(deadline);
					resolve(unavailable);
				});
				child.stdout.setEncoding("utf8");
				child.stdout.on("data", (data: string) => {
					stdout += data;
					if (stdout.length > 65_000) child.kill();
				});
				child.once("close", () => {
					clearTimeout(deadline);
					try {
						const result = JSON.parse(stdout) as unknown;
						resolve(
							result && typeof result === "object" && !Array.isArray(result)
								? (result as Record<string, unknown>)
								: unavailable,
						);
					} catch {
						resolve(unavailable);
					}
				});
				child.stdin.end(
					JSON.stringify({
						decision_source: "pm-evidence",
						proof_id: id,
						proof_nonce: nonce,
						...(reconcile ? { reconcile: true } : {}),
					}),
				);
			});
		let result = await run(false);
		if (prepared !== undefined && result.conclusion !== "finalize") {
			// Recover the original operation with its live proof and existing bytes.
			// The reconciliation child cannot publish or replace a file.
			const recovered = await run(true);
			result =
				recovered.signoff_status === "reconciled"
					? recovered
					: { ...result, ...recovered, signoff_status: "effect-unknown" };
		}
		writeAllowed = false;
		if (publication !== undefined) {
			// A timed-out child may have published before emitting its receipt.
			setTimeout(() => server.close(), 90 * 60_000).unref();
		} else {
			server.close();
		}
		return result;
	} catch {
		server.close();
		return unavailable;
	}
}
