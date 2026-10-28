/**
 * RAG config layer tests (mw-rag-integration T-01; design D-003/D-009,
 * VC-002/VC-024).
 *
 * The machine layer is injected through MW_RAG_SERVERS_FILE; the project layer
 * and the `rag:` section live in a fresh temp control root. Every assertion
 * runs through the real fs reader, so the two-layer precedence, the per-field
 * origin bookkeeping and the fingerprint scope are exercised end to end.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { RagServerEntry } from "../../src/extensions/agent-team-loop/rag/config.ts";
import {
	ENV_RAG_SERVERS_FILE,
	ENV_RAG_SERVERS_HOME,
	loadRagConfig,
	machineRagServersPath,
	RagConfigError,
	ragFingerprint,
	requiredFor,
	resolveDefaults,
} from "../../src/extensions/agent-team-loop/rag/config.ts";

const tmpDirs: string[] = [];
const originalServersFile = process.env[ENV_RAG_SERVERS_FILE];

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tmpDirs.push(dir);
	return dir;
}

afterEach(() => {
	if (originalServersFile === undefined) delete process.env[ENV_RAG_SERVERS_FILE];
	else process.env[ENV_RAG_SERVERS_FILE] = originalServersFile;
	for (const dir of tmpDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

/** Write the machine service table and point MW_RAG_SERVERS_FILE at it. */
function writeMachine(content: string): string {
	const dir = mkdtemp("mw-rag-machine-");
	const file = path.join(dir, "rag-servers.yml");
	fs.writeFileSync(file, content, "utf-8");
	process.env[ENV_RAG_SERVERS_FILE] = file;
	return file;
}

function writeTarget(controlRoot: string, content: string): void {
	fs.mkdirSync(path.join(controlRoot, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(path.join(controlRoot, ".agenticdoc", "target.yml"), content, "utf-8");
}

function writeProjectServers(controlRoot: string, content: string): void {
	fs.mkdirSync(path.join(controlRoot, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(controlRoot, ".mw", "rag-servers.yml"), content, "utf-8");
}

function expectRagError(fn: () => unknown, kind: string, messageIncludes?: string): RagConfigError {
	let caught: unknown;
	try {
		fn();
	} catch (err) {
		caught = err;
	}
	expect(caught).toBeInstanceOf(RagConfigError);
	const error = caught as RagConfigError;
	expect(error.kind).toBe(kind);
	if (messageIncludes !== undefined) expect(error.message).toContain(messageIncludes);
	return error;
}

const MACHINE_FULL = `servers:
  A:
    transport: both
    mcp:
      url: http://machine.example/a
      token_env: MACHINE_TOKEN
      timeout_ms: 1000
    skill:
      dir: /machine/skill
      cli_entry: scripts/cli.py
      timeout_ms: 2000
    adapter: overcode-v1
    path_roots_file: /machine/path-roots.json
    sources:
      - engine
      - game
    capabilities:
      graph: true
      chat: false
      rewrite: true
  B:
    transport: mcp
    mcp:
      url: http://machine.example/b
    sources:
      - engine
`;

describe("loadRagConfig two-layer merge", () => {
	it("merges field-by-field, replaces arrays, deletes with null and records origin (VC-024)", () => {
		writeMachine(MACHINE_FULL);
		const controlRoot = mkdtemp("mw-rag-control-");
		writeTarget(controlRoot, "rag:\n  enabled: [A]\n  default_server: A\n");

		// Project overrides only A.mcp.url; everything else inherits.
		writeProjectServers(
			controlRoot,
			`servers:
  A:
    mcp:
      url: http://project.example/a
`,
		);
		const inherited = loadRagConfig(controlRoot);
		const a = inherited.servers.A;
		expect(a).toBeDefined();
		expect(a.mcp?.url).toBe("http://project.example/a");
		expect(a.mcp?.tokenEnv).toBe("MACHINE_TOKEN");
		expect(a.mcp?.timeoutMs).toBe(1000);
		expect(a.skill).toEqual({ dir: "/machine/skill", cliEntry: "scripts/cli.py", timeoutMs: 2000 });
		expect(a.capabilities).toEqual({ graph: true, chat: false, rewrite: true });
		expect(a.sources).toEqual(["engine", "game"]);
		expect(a.transport).toBe("both");
		expect(a.pathRootsFile).toBe("/machine/path-roots.json");
		expect(a.origin["mcp.url"]).toBe("project");
		expect(a.origin["mcp.token_env"]).toBe("machine");
		expect(a.origin["mcp.timeout_ms"]).toBe("machine");
		expect(a.origin["capabilities.graph"]).toBe("machine");
		expect(a.origin.sources).toBe("machine");
		expect(a.origin.transport).toBe("machine");
		expect(a.origin.path_roots_file).toBe("machine");

		// Arrays replace wholesale ([] clears); null deletes the block. Deleting
		// the skill block also requires narrowing transport (fail-closed).
		writeProjectServers(
			controlRoot,
			`servers:
  A:
    transport: mcp
    mcp:
      url: http://project.example/a
    sources: []
    skill: null
`,
		);
		const replaced = loadRagConfig(controlRoot);
		const replacedA = replaced.servers.A;
		expect(replacedA.sources).toEqual([]);
		expect(replacedA.origin.sources).toBe("project");
		expect(replacedA.skill).toBeNull();
		expect(replacedA.origin.skill).toBe("project");
		expect(replacedA.transport).toBe("mcp");
		expect(replacedA.origin.transport).toBe("project");

		// Server B is untouched by the A merge.
		const b = replaced.servers.B;
		expect(b.mcp?.url).toBe("http://machine.example/b");
		expect(b.sources).toEqual(["engine"]);
		expect(b.origin["mcp.url"]).toBe("machine");
		expect(b.origin.sources).toBe("machine");

		process.stdout.write(
			"[VERIFY] VC-024: field_merge=true array_replace=true null_delete=true origin_per_field=true\n",
		);
	});

	it("marks the project value and origin for an overlapping server (VC-002)", () => {
		writeMachine(`servers:
  S:
    mcp:
      url: http://machine.example/s
    sources:
      - engine
`);
		const controlRoot = mkdtemp("mw-rag-control-");
		writeTarget(controlRoot, "rag:\n  enabled: [S]\n");
		writeProjectServers(
			controlRoot,
			`servers:
  S:
    mcp:
      url: http://project.example/s
`,
		);
		const config = loadRagConfig(controlRoot);
		const urlMatch = config.servers.S.mcp?.url === "http://project.example/s";
		const origin = config.servers.S.origin["mcp.url"];
		expect(urlMatch).toBe(true);
		expect(origin).toBe("project");
		process.stdout.write(`[VERIFY] VC-002: server=S url_match=${urlMatch} origin=${origin}\n`);
	});
});

describe("loadRagConfig validation", () => {
	it("rejects an enabled server that is not defined", () => {
		writeMachine(MACHINE_FULL);
		const controlRoot = mkdtemp("mw-rag-control-");
		writeTarget(controlRoot, "rag:\n  enabled: [A, MISSING]\n");
		const error = expectRagError(() => loadRagConfig(controlRoot), "unknown-server", "MISSING");
		expect(error.message).toContain("visible: A, B");
	});

	it("rejects an empty enabled entry", () => {
		writeMachine(MACHINE_FULL);
		const controlRoot = mkdtemp("mw-rag-control-");
		writeTarget(controlRoot, 'rag:\n  enabled: ["A", "  "]\n');
		expectRagError(() => loadRagConfig(controlRoot), "enabled-empty-entry");
	});

	it("rejects a skill transport without cli_entry", () => {
		writeMachine(`servers:
  T:
    transport: skill
    skill:
      dir: /skill
`);
		const controlRoot = mkdtemp("mw-rag-control-");
		writeTarget(controlRoot, "rag:\n  enabled: [T]\n");
		expectRagError(() => loadRagConfig(controlRoot), "skill-missing-cli", "T");
	});

	it("rejects an mcp transport without url", () => {
		writeMachine(`servers:
  U:
    transport: mcp
    mcp:
      token_env: SOME_TOKEN
`);
		const controlRoot = mkdtemp("mw-rag-control-");
		writeTarget(controlRoot, "rag:\n  enabled: [U]\n");
		expectRagError(() => loadRagConfig(controlRoot), "mcp-missing-url", "U");
	});

	it("rejects unknown top-level and server keys", () => {
		writeMachine("servers:\n  A:\n    mcp:\n      url: http://x/a\n    bogus: 1\n");
		const controlRoot = mkdtemp("mw-rag-control-");
		writeTarget(controlRoot, "rag:\n  enabled: [A]\n");
		expectRagError(() => loadRagConfig(controlRoot), "unknown-key", "bogus");

		writeMachine("servers:\n  A:\n    mcp:\n      url: http://x/a\nunexpected: 1\n");
		expectRagError(() => loadRagConfig(controlRoot), "unknown-key", "unexpected");
	});

	it("returns enabled=[] without throwing when no config exists", () => {
		const controlRoot = mkdtemp("mw-rag-control-");
		const config = loadRagConfig(controlRoot);
		expect(config.enabled).toEqual([]);
		expect(config.defaultServer).toBeNull();
		expect(config.servers).toEqual({});
		expect(config.budgets).toEqual({ chat: 2, timeS: 900 });
		expect(config.fingerprint).toMatch(/^[0-9a-f]{64}$/);
	});
});

describe("required union and default resolution", () => {
	it("unions role.require and phase.require", () => {
		writeMachine(MACHINE_FULL);
		const controlRoot = mkdtemp("mw-rag-control-");
		writeTarget(
			controlRoot,
			`rag:
  enabled: [A]
  roles:
    review:
      require: true
  phases:
    design:
      require: true
    coding:
      require: false
`,
		);
		const config = loadRagConfig(controlRoot);
		expect(requiredFor(config, "review", "any-phase")).toBe(true);
		expect(requiredFor(config, "coding", "design")).toBe(true);
		expect(requiredFor(config, "coding", "coding")).toBe(false);
	});

	it("resolves role > phase > defaultServer and the research rewrite default", () => {
		writeMachine(MACHINE_FULL);
		const controlRoot = mkdtemp("mw-rag-control-");
		writeTarget(
			controlRoot,
			`rag:
  enabled: [A, B]
  default_server: B
  roles:
    spec:
      server: A
      source: engine
    review:
      server: B
      rewrite: false
  phases:
    design:
      server: A
`,
		);
		const config = loadRagConfig(controlRoot);
		// Research role on a rewrite-capable server: capability drives the default.
		const spec = resolveDefaults(config, "spec", "");
		expect(spec.server).toBe("A");
		expect(spec.source).toBe("engine");
		expect(spec.rewrite).toBe(true);
		// coding is not research-like: no rewrite default (default server is B,
		// which has no rewrite capability either).
		expect(resolveDefaults(config, "coding", "")).toEqual({ server: "B", source: null, rewrite: false });
		// role declaration (B) wins over the phase declaration (A); the explicit
		// role `rewrite: false` also wins over the research phase default.
		expect(resolveDefaults(config, "review", "design")).toEqual({ server: "B", source: null, rewrite: false });
		// A research phase alone trips the rewrite default and the phase-declared
		// server beats `default_server: B` (the D-102 shadowing fix).
		const phaseOnly = resolveDefaults(config, "coding", "design");
		expect(phaseOnly).toEqual({ server: "A", source: null, rewrite: true });
		// Empty axes stay at `default_server` / null / false (D-103).
		expect(resolveDefaults(config, "", "")).toEqual({ server: "B", source: null, rewrite: false });
	});
});

describe("fingerprint scope (D-009)", () => {
	function setup(): { controlRoot: string; rootsFile: string } {
		const rootsFile = path.join(mkdtemp("mw-rag-roots-"), "path-roots.json");
		fs.writeFileSync(rootsFile, JSON.stringify({ engine: "/mnt/engine" }), "utf-8");
		writeMachine(`servers:
  A:
    mcp:
      url: http://machine.example/a
    path_roots_file: ${rootsFile}
    capabilities:
      rewrite: true
  B:
    mcp:
      url: http://machine.example/b
`);
		const controlRoot = mkdtemp("mw-rag-control-");
		writeTarget(controlRoot, "rag:\n  enabled: [A]\n  roles:\n    spec: {}\n");
		return { controlRoot, rootsFile };
	}

	it("ignores non-enabled servers and health/probe state, tracks url and path_roots content", () => {
		const { controlRoot, rootsFile } = setup();
		const baseline = loadRagConfig(controlRoot);
		expect(loadRagConfig(controlRoot).fingerprint).toBe(baseline.fingerprint);

		// Changing the enabled server's url is a tear.
		writeMachine(`servers:
  A:
    mcp:
      url: http://machine.example/a-v2
    path_roots_file: ${rootsFile}
    capabilities:
      rewrite: true
  B:
    mcp:
      url: http://machine.example/b
`);
		expect(loadRagConfig(controlRoot).fingerprint).not.toBe(baseline.fingerprint);

		// Changing the path_roots file content is a tear (url back to baseline).
		fs.writeFileSync(rootsFile, JSON.stringify({ engine: "/mnt/engine-v2" }), "utf-8");
		writeMachine(`servers:
  A:
    mcp:
      url: http://machine.example/a
    path_roots_file: ${rootsFile}
    capabilities:
      rewrite: true
  B:
    mcp:
      url: http://machine.example/b
`);
		expect(loadRagConfig(controlRoot).fingerprint).not.toBe(baseline.fingerprint);

		// Changing a non-enabled server keeps the fingerprint stable.
		fs.writeFileSync(rootsFile, JSON.stringify({ engine: "/mnt/engine" }), "utf-8");
		writeMachine(`servers:
  A:
    mcp:
      url: http://machine.example/a
    path_roots_file: ${rootsFile}
    capabilities:
      rewrite: true
  B:
    mcp:
      url: http://machine.example/b-changed
`);
		const afterUnrelated = loadRagConfig(controlRoot);
		expect(afterUnrelated.fingerprint).toBe(baseline.fingerprint);

		// Probe/health annotations are runtime state, never part of the digest.
		const entry = afterUnrelated.servers.A as RagServerEntry & { health?: string; probe?: string };
		entry.health = "degraded";
		entry.probe = "unreachable";
		expect(ragFingerprint(afterUnrelated)).toBe(baseline.fingerprint);
	});
});

describe("machineRagServersPath (D-013)", () => {
	it("prefers MW_RAG_SERVERS_FILE, then MW_RAG_SERVERS_HOME, then HOME, then USERPROFILE", () => {
		expect(
			machineRagServersPath({
				[ENV_RAG_SERVERS_FILE]: "/tmp/explicit.yml",
				[ENV_RAG_SERVERS_HOME]: "/tmp/home",
				HOME: "/tmp/home2",
				USERPROFILE: "C:\\Users\\x",
			}),
		).toBe("/tmp/explicit.yml");
		expect(machineRagServersPath({ [ENV_RAG_SERVERS_HOME]: "/tmp/home", HOME: "/tmp/home2" })).toBe(
			path.join("/tmp/home", ".agents", "rag-servers.yml"),
		);
		expect(machineRagServersPath({ HOME: "/tmp/home2", USERPROFILE: "C:\\Users\\x" })).toBe(
			path.join("/tmp/home2", ".agents", "rag-servers.yml"),
		);
		expect(machineRagServersPath({ USERPROFILE: "C:\\Users\\x" })).toBe(
			path.join("C:\\Users\\x", ".agents", "rag-servers.yml"),
		);
		expect(machineRagServersPath({})).toBe("");
	});
});
