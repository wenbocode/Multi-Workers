/**
 * Padded-value parity lock (mw-rag-window-parity T-3C, VC-305b).
 *
 * T-4 (independent verification) found that Python `_rag_finalize_mcp` /
 * `_rag_finalize_skill` store `.strip()`ed strings (`mw_common.py:534-538,
 * 564-565`) while the TS loader kept the padding, so the same config file
 * produced two different fingerprints (the exact `config tear (rag)` symptom
 * AC-302 exists to prevent). The TS side now trims the same four fields
 * (`mcp.url`, `mcp.token_env`, `skill.dir`, `skill.cli_entry`).
 *
 * Every case compares the shipped TS loader against a real Python subprocess -
 * never a hand-copied constant - and also asserts the parsed TS values, so a
 * regression that only trims for hashing (or only for values) still fails.
 *
 * Deliberately NOT trimmed: `path_roots_file`, because Python hashes the
 * stripped field but computes the digest from the untrimmed string
 * (`mw_common.py:636-637`); that residual divergence is declared as 遗留 R-6
 * in the key's achieved.md instead of being papered over here.
 */

import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import { resolveRagPython } from "../../src/extensions/agent-team-loop/rag/cli-bridge.ts";
import {
	ENV_RAG_SERVERS_FILE,
	ENV_RAG_SERVERS_HOME,
	loadRagConfig,
	RagConfigError,
} from "../../src/extensions/agent-team-loop/rag/config.ts";

function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

const MULTI_WORKERS_DIR = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));
const tmpDirs: string[] = [];
const originalServersFile = process.env[ENV_RAG_SERVERS_FILE];
const originalServersHome = process.env[ENV_RAG_SERVERS_HOME];

const pythonAvailable = (() => {
	try {
		return (
			spawnSync(resolveRagPython(), ["-c", "import yaml; print(1)"], { encoding: "utf8", timeout: 10_000 })
				.status === 0
		);
	} catch {
		return false;
	}
})();

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tmpDirs.push(dir);
	return dir;
}

afterEach(() => {
	if (originalServersFile === undefined) delete process.env[ENV_RAG_SERVERS_FILE];
	else process.env[ENV_RAG_SERVERS_FILE] = originalServersFile;
	if (originalServersHome === undefined) delete process.env[ENV_RAG_SERVERS_HOME];
	else process.env[ENV_RAG_SERVERS_HOME] = originalServersHome;
	for (const dir of tmpDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

/** A control root whose project RAG layer is exactly `serversYml`. */
function serversRoot(serversYml: string, enabled: string[]): string {
	const root = mkdtemp("mw-rag-trim-");
	fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
	fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(path.join(root, ".mw", "rag-servers.yml"), serversYml, "utf-8");
	fs.writeFileSync(
		path.join(root, ".agenticdoc", "target.yml"),
		`rag:\n  enabled: [${enabled.join(", ")}]\n`,
		"utf-8",
	);
	return root;
}

/** The Python loader's verdict for one control root: fingerprint or error. */
function pythonLoad(root: string): { fingerprint?: string; error?: string } {
	const script = [
		"import json, pathlib, sys",
		"sys.path.insert(0, sys.argv[1])",
		"import mw_common",
		"config, error = mw_common.load_rag_config(pathlib.Path(sys.argv[2]))",
		"if error:",
		"    print(json.dumps({'error': error}))",
		"else:",
		"    print(json.dumps({'fingerprint': mw_common.rag_fingerprint(config)}))",
	].join("\n");
	const env = {
		...process.env,
		[ENV_RAG_SERVERS_FILE]: path.join(root, "absent-machine.yml"),
		[ENV_RAG_SERVERS_HOME]: root,
	};
	const result = spawnSync(resolveRagPython(), ["-c", script, MULTI_WORKERS_DIR, root], {
		encoding: "utf8",
		timeout: 30_000,
		env,
	});
	if (result.status !== 0) {
		throw new Error(`python load failed (status=${String(result.status)}): ${result.stderr ?? ""}`);
	}
	return JSON.parse(result.stdout ?? "{}") as { fingerprint?: string; error?: string };
}

/** Isolate the TS loader from the machine layer before every load. */
function tsLoad(root: string) {
	process.env[ENV_RAG_SERVERS_FILE] = path.join(root, "absent-machine.yml");
	process.env[ENV_RAG_SERVERS_HOME] = root;
	return loadRagConfig(root);
}

const PADDED_SKILL_YML =
	"servers:\n" +
	"  S:\n" +
	"    transport: skill\n" +
	'    skill:\n      dir: "  skills/x  "\n      cli_entry: "  cli.py  "\n';

const PADDED_MCP_YML =
	"servers:\n" +
	"  S:\n" +
	"    transport: mcp\n" +
	"    mcp:\n" +
	'      url: "  http://127.0.0.1:19999/  "\n' +
	'      token_env: "  RAG_TOKEN  "\n';

const BLANK_ONLY_YML =
	"servers:\n  S:\n    transport: skill\n    skill:\n" + '      dir: "   "\n      cli_entry: cli.py\n';

describe("padded RAG field parity (VC-305b)", () => {
	it.skipIf(!pythonAvailable)("trims skill.dir / skill.cli_entry like Python and keeps the fingerprint equal", () => {
		const root = serversRoot(PADDED_SKILL_YML, ["S"]);
		const config = tsLoad(root);
		expect(config.servers.S.skill?.dir).toBe("skills/x");
		expect(config.servers.S.skill?.cliEntry).toBe("cli.py");
		const python = pythonLoad(root);
		expect(python.error).toBeUndefined();
		expect(config.fingerprint).toBe(python.fingerprint);
		verify(
			`[VERIFY] VC-305b: dir="${config.servers.S.skill?.dir}" cli_entry="${
				config.servers.S.skill?.cliEntry
			}" ts==py=${config.fingerprint === python.fingerprint} prefix=${config.fingerprint.slice(0, 12)}`,
		);
	});

	it.skipIf(!pythonAvailable)("trims mcp.url / mcp.token_env like Python and keeps the fingerprint equal", () => {
		const root = serversRoot(PADDED_MCP_YML, ["S"]);
		const config = tsLoad(root);
		expect(config.servers.S.mcp?.url).toBe("http://127.0.0.1:19999/");
		expect(config.servers.S.mcp?.tokenEnv).toBe("RAG_TOKEN");
		const python = pythonLoad(root);
		expect(python.error).toBeUndefined();
		expect(config.fingerprint).toBe(python.fingerprint);
		verify(
			`[VERIFY] VC-305b: url="${config.servers.S.mcp?.url}" token_env="${
				config.servers.S.mcp?.tokenEnv
			}" ts==py=${config.fingerprint === python.fingerprint} prefix=${config.fingerprint.slice(0, 12)}`,
		);
	});

	it.skipIf(!pythonAvailable)("rejects a whitespace-only skill.dir on both sides", () => {
		const root = serversRoot(BLANK_ONLY_YML, ["S"]);
		let tsError: RagConfigError | null = null;
		try {
			tsLoad(root);
		} catch (error) {
			tsError = error as RagConfigError;
		}
		expect(tsError).toBeInstanceOf(RagConfigError);
		expect(tsError?.kind).toBe("invalid-shape");
		const python = pythonLoad(root);
		expect(python.error).toContain("skill.dir");
		verify(`[VERIFY] VC-305b: blank_dir_ts_kind=${tsError?.kind} blank_dir_py_error=${python.error !== undefined}`);
	});
});

// The machine layer is what the window's doctor call reads; keeping the
// override names asserted here prevents a rename from silently re-enabling the
// developer's real ~/.agents/rag-servers.yml inside the suite.
describe("parity harness isolation (VC-305b)", () => {
	it("uses the documented machine-layer override names", () => {
		expect(ENV_RAG_SERVERS_FILE).toBe("MW_RAG_SERVERS_FILE");
		expect(ENV_RAG_SERVERS_HOME).toBe("MW_RAG_SERVERS_HOME");
	});
});
