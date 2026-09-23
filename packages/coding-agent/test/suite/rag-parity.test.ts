/**
 * TS <-> Python RAG config cross-language parity lock (mw-rag-integration
 * T-12-PARITY-LOCK, VC-027).
 *
 * The Python side (packages/multi-workers/mw_common.py, T-06) is the source of
 * truth: `test_rag_config.py` and `test/fixtures/rag-block.golden.md` pin the
 * contract. This suite reads the SAME shared fixtures (never a copy) and
 * asserts:
 *   - the TS `ragFingerprint` equals the fingerprint embedded in the golden
 *     block (the most sensitive drift probe: one field, one canonical-JSON
 *     rule or one snake_case key moving breaks it),
 *   - the `origin` evaluated field paths are snake_case and equal the Python
 *     set,
 *   - the shared fixtures are byte-identical to the digests T-06 recorded,
 *   - the shared error categories (`unknown-key` / `unknown-server`) are the
 *     same on both sides.
 *
 * The golden block itself is rendered by `rag/block.ts` (T-04); now that it
 * exists this suite asserts the byte equality directly (T-04's
 * `rag-tools.test.ts` may assert it too).
 */

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import { renderRagBlock } from "../../src/extensions/agent-team-loop/rag/block.ts";
import { resolveRagPython } from "../../src/extensions/agent-team-loop/rag/cli-bridge.ts";
import {
	ENV_RAG_SERVERS_FILE,
	loadRagConfig,
	RAG_FIELD_CAMEL,
	RagConfigError,
	ragFingerprint,
	resolveDefaults,
} from "../../src/extensions/agent-team-loop/rag/config.ts";

// ── shared fixtures (T-06 output.md digests) ────────────────────────────────

const RAG_FIXTURES = fileURLToPath(new URL("../../../multi-workers/test/fixtures/rag/", import.meta.url));
const GOLDEN_FILE = fileURLToPath(new URL("../../../multi-workers/test/fixtures/rag-block.golden.md", import.meta.url));
const MACHINE_FIXTURE = path.join(RAG_FIXTURES, "machine-servers.yml");
const PROJECT_FIXTURE = path.join(RAG_FIXTURES, "project-servers.yml");
const TARGET_FIXTURE = path.join(RAG_FIXTURES, "target.yml");
const PHASE_ONLY_TARGET = path.join(RAG_FIXTURES, "phase-only-target.yml");
const ROOTS_FIXTURE = path.join(RAG_FIXTURES, "rag-roots.json");

/** sha256 recorded by T-06 (`workers/mw-rag-t06-py-config/output.md`). */
const FIXTURE_SHA256: Record<string, string> = {
	[MACHINE_FIXTURE]: "99c745c0bd87e9a753a40460099994dfc5a21de348976d1c0e41cca6f108ff7c",
	[PROJECT_FIXTURE]: "44d1980e814c82fea14b48cebeb97a6512f13fea2748b077d64216da99a40938",
	[TARGET_FIXTURE]: "6594c7e54e10b452e94c1bd14f70811a7da494592ec6c5817cda4abbde3d0025",
	[ROOTS_FIXTURE]: "ea1700891c38012b266c3e52443cc12b956da98eb1989a23ba30478cdf048763",
};

/** Golden block sha256 / byte length recorded by T-06. */
const GOLDEN_SHA256 = "00f85e646e30d577f434c6e1967a704c65966163a01d1bf4de9630c9717d4035";
const GOLDEN_FINGERPRINT = "436b6a35ff60162559fe45e07f80afbe4c7e1c3e044bb6cc3c17196356034950";
const GOLDEN_LENGTH = 347;

/** snake_case `origin` paths emitted by Python `load_rag_config` on the fixture. */
const EXPECTED_ORIGIN_A = [
	"adapter",
	"capabilities.chat",
	"capabilities.graph",
	"capabilities.rewrite",
	"mcp.timeout_ms",
	"mcp.token_env",
	"mcp.url",
	"path_roots_file",
	"skill.cli_entry",
	"skill.dir",
	"skill.timeout_ms",
	"sources",
	"transport",
].sort();
const EXPECTED_ORIGIN_B = [
	"capabilities.chat",
	"capabilities.graph",
	"capabilities.rewrite",
	"mcp.url",
	"transport",
].sort();

const originalServersFile = process.env[ENV_RAG_SERVERS_FILE];
const tmpDirs: string[] = [];

afterEach(() => {
	if (originalServersFile === undefined) delete process.env[ENV_RAG_SERVERS_FILE];
	else process.env[ENV_RAG_SERVERS_FILE] = originalServersFile;
	for (const dir of tmpDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tmpDirs.push(dir);
	return dir;
}

function sha256(file: string): string {
	return createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

/** Build a control root that carries the shared project fixtures. */
function fixtureRoot(): string {
	const root = mkdtemp("mw-rag-parity-");
	fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
	fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
	fs.copyFileSync(PROJECT_FIXTURE, path.join(root, ".mw", "rag-servers.yml"));
	fs.copyFileSync(ROOTS_FIXTURE, path.join(root, ".mw", "rag-roots.json"));
	fs.copyFileSync(TARGET_FIXTURE, path.join(root, ".agenticdoc", "target.yml"));
	process.env[ENV_RAG_SERVERS_FILE] = MACHINE_FIXTURE;
	return root;
}

/** Inverse of `RAG_FIELD_CAMEL`: camelCase segment -> snake_case. */
const CAMEL_TO_SNAKE: Record<string, string> = {};
for (const [snake, camel] of Object.entries(RAG_FIELD_CAMEL)) CAMEL_TO_SNAKE[camel] = snake;

function snakePath(key: string): string {
	return key
		.split(".")
		.map((segment) => CAMEL_TO_SNAKE[segment] ?? segment)
		.join(".");
}

/** Repo `packages/multi-workers` (the Python ground truth sources). */
const MULTI_WORKERS_DIR = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));

/** Python availability probe: the VC-305 subprocess run is skipped without it. */
const pythonAvailable = (() => {
	try {
		return spawnSync(resolveRagPython(), ["-c", "print(1)"], { encoding: "utf8", timeout: 10_000 }).status === 0;
	} catch {
		return false;
	}
})();

/**
 * Python ground truth for a control root: `mw_common.load_rag_config` then
 * `mw_common.rag_fingerprint`, run as a real subprocess so the TS signature is
 * compared against the shipped Python bytes, not a hand-copied constant.
 */
function pythonFingerprint(root: string): string {
	const script = [
		"import pathlib, sys",
		"sys.path.insert(0, sys.argv[1])",
		"import mw_common",
		"config, error = mw_common.load_rag_config(pathlib.Path(sys.argv[2]))",
		"if error:",
		"    print('ERROR: ' + error)",
		"    sys.exit(3)",
		"print(mw_common.rag_fingerprint(config))",
	].join("\n");
	const result = spawnSync(resolveRagPython(), ["-c", script, MULTI_WORKERS_DIR, root], {
		encoding: "utf8",
		timeout: 30_000,
		env: process.env,
	});
	if (result.status !== 0) {
		throw new Error(
			`python rag_fingerprint failed (status=${String(result.status)}): ${result.stdout ?? ""}${result.stderr ?? ""}`,
		);
	}
	return (result.stdout ?? "").trim();
}

/**
 * A control root with one project-layer `skill` server carrying the given
 * `skill` sub-block lines (6-space indent). The machine layer is pointed at a
 * non-existent file so both loaders see an empty machine layer.
 */
function dirVariantRoot(skillLines: string[]): string {
	const root = mkdtemp("mw-rag-parity-dir-");
	fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
	fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
	const lines = ["servers:", "  S:", "    transport: skill", "    skill:", ...skillLines];
	fs.writeFileSync(path.join(root, ".mw", "rag-servers.yml"), `${lines.join("\n")}\n`, "utf-8");
	fs.writeFileSync(path.join(root, ".agenticdoc", "target.yml"), "rag:\n  enabled: [S]\n", "utf-8");
	process.env[ENV_RAG_SERVERS_FILE] = path.join(root, "absent-machine.yml");
	return root;
}

// ── VC-027: fingerprint parity ──────────────────────────────────────────────

describe("RAG cross-language parity (VC-027)", () => {
	it("hashes the shared fixtures exactly like the Python golden fingerprint", () => {
		const root = fixtureRoot();
		const config = loadRagConfig(root);

		// The fingerprint embedded in the Python-rendered golden block.
		const golden = fs.readFileSync(GOLDEN_FILE, "utf-8");
		const match = /^fingerprint=([0-9a-f]{64})$/m.exec(golden);
		expect(match).not.toBeNull();
		const goldenFingerprint = match?.[1] ?? "";

		expect(config.fingerprint).toBe(goldenFingerprint);
		expect(config.fingerprint).toBe(GOLDEN_FINGERPRINT);
		// Rehashing a loaded config is stable and honours the enabled override.
		expect(ragFingerprint(config)).toBe(goldenFingerprint);
		expect(ragFingerprint(config, config.enabled)).toBe(goldenFingerprint);

		// Fixture digest parity: if these move, the fixtures changed under the
		// contract and the test must stop instead of chasing the expectation.
		for (const [file, digest] of Object.entries(FIXTURE_SHA256)) {
			expect(sha256(file), `fixture digest drift: ${path.basename(file)}`).toBe(digest);
		}
	});

	it("keeps the snake_case field mapping table identical to Python RAG_FIELD_CAMEL", () => {
		expect(RAG_FIELD_CAMEL).toEqual({
			token_env: "tokenEnv",
			timeout_ms: "timeoutMs",
			cli_entry: "cliEntry",
			path_roots_file: "pathRootsFile",
			default_server: "defaultServer",
			chat_budget: "chatBudget",
			time_budget_s: "timeBudgetS",
		});
	});

	it("records the identical snake_case origin table as Python", () => {
		const root = fixtureRoot();
		const config = loadRagConfig(root);
		const a = config.servers.A;
		const b = config.servers.B;

		// Normalising must be a no-op: TS writes snake_case paths directly, so a
		// camelCase leak shows up as a raw/normalised mismatch.
		const originA = Object.fromEntries(Object.entries(a.origin).map(([key, value]) => [snakePath(key), value]));
		const originB = Object.fromEntries(Object.entries(b.origin).map(([key, value]) => [snakePath(key), value]));
		expect(Object.keys(originA).sort()).toEqual(EXPECTED_ORIGIN_A);
		expect(Object.keys(originB).sort()).toEqual(EXPECTED_ORIGIN_B);
		expect(Object.keys(a.origin).sort()).toEqual(EXPECTED_ORIGIN_A);
		expect(Object.keys(b.origin).sort()).toEqual(EXPECTED_ORIGIN_B);

		// Per-field spot checks against the Python fixture result.
		expect(originA["mcp.url"]).toBe("project"); // project layer wins the url
		expect(originA["mcp.token_env"]).toBe("machine"); // inherited from machine
		expect(originA.sources).toBe("machine"); // fixture: only the url is overridden
		expect(originA.skill).toBeUndefined(); // block-level origin is only set on delete
		expect(originA["skill.cli_entry"]).toBe("machine");
		expect(originB["mcp.url"]).toBe("machine");
	});

	it("records a project origin for an overridden snake_case sources list", () => {
		const root = mkdtemp("mw-rag-parity-sources-");
		fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
		fs.writeFileSync(
			path.join(root, ".mw", "rag-servers.yml"),
			"servers:\n  A:\n    sources:\n      - docs\n",
			"utf-8",
		);
		process.env[ENV_RAG_SERVERS_FILE] = MACHINE_FIXTURE;
		const config = loadRagConfig(root);
		expect(config.servers.A.origin.sources).toBe("project");
		expect(config.servers.A.origin["mcp.url"]).toBe("machine");
	});

	// ── error categories (unknown-key / unknown-server are shared names) ─────

	it("uses the shared unknown-key / unknown-server categories", () => {
		const root = fixtureRoot();
		fs.writeFileSync(path.join(root, ".agenticdoc", "target.yml"), "rag:\n  enabled: [A]\n  bogus_key: 1\n", "utf-8");
		let unknownKey: unknown;
		try {
			loadRagConfig(root);
		} catch (error) {
			unknownKey = error;
		}
		expect(unknownKey).toBeInstanceOf(RagConfigError);
		expect((unknownKey as RagConfigError).kind).toBe("unknown-key");

		fs.writeFileSync(path.join(root, ".agenticdoc", "target.yml"), "rag:\n  enabled: [Z]\n", "utf-8");
		let unknownServer: unknown;
		try {
			loadRagConfig(root);
		} catch (error) {
			unknownServer = error;
		}
		expect(unknownServer).toBeInstanceOf(RagConfigError);
		expect((unknownServer as RagConfigError).kind).toBe("unknown-server");
		expect((unknownServer as RagConfigError).message).toContain("'Z'");
	});

	// ── golden byte contract + single consolidated VC-027 line ──────────────

	it("renders the golden block byte-for-byte through rag/block.ts", () => {
		const root = fixtureRoot();
		const config = loadRagConfig(root);
		const golden = fs.readFileSync(GOLDEN_FILE);
		const meta = { type: "coding", role: "coding", phase: "execute" };
		const block = renderRagBlock(config, meta);
		expect(block).not.toBeNull();
		// Byte-equal incl. the "no trailing newline" shape of the golden.
		expect(Buffer.from(block ?? "", "utf-8").equals(golden)).toBe(true);
		// Idempotent re-render.
		expect(renderRagBlock(config, meta)).toBe(block);
	});

	it("keeps the golden byte contract and reports VC-027", () => {
		const bytes = fs.readFileSync(GOLDEN_FILE);
		expect(bytes.length).toBe(GOLDEN_LENGTH);
		expect(sha256(GOLDEN_FILE)).toBe(GOLDEN_SHA256);
		// No trailing newline: the golden is exactly the block.
		expect(bytes[bytes.length - 1]).not.toBe(0x0a);
		const text = bytes.toString("utf-8");
		expect(text.startsWith("<!-- mw-rag: v1 -->\n")).toBe(true);
		expect(text.endsWith(`fingerprint=${GOLDEN_FINGERPRINT}`)).toBe(true);

		const root = fixtureRoot();
		const config = loadRagConfig(root);
		const fingerprintMatch = config.fingerprint === GOLDEN_FINGERPRINT;
		const originTableMatch =
			JSON.stringify(Object.keys(config.servers.A.origin).sort()) === JSON.stringify(EXPECTED_ORIGIN_A) &&
			JSON.stringify(Object.keys(config.servers.B.origin).sort()) === JSON.stringify(EXPECTED_ORIGIN_B);
		const fixtureDigestMatch = Object.entries(FIXTURE_SHA256).every(([file, digest]) => sha256(file) === digest);
		const rendered = renderRagBlock(config, { type: "coding", role: "coding", phase: "execute" });
		const goldenByteMatch = rendered !== null && Buffer.from(rendered, "utf-8").equals(bytes);
		expect(fingerprintMatch).toBe(true);
		expect(originTableMatch).toBe(true);
		expect(fixtureDigestMatch).toBe(true);
		expect(goldenByteMatch).toBe(true);
		// process.stdout.write, not console.log: the suite config uses silent: "passed-only",
		// which swallows console.log from green tests and would hide this evidence line.
		process.stdout.write(
			"[VERIFY] VC-027: " +
				`golden_byte_match=${goldenByteMatch} fingerprint_match=${fingerprintMatch} ` +
				`origin_table_match=${originTableMatch} fixture_digest_match=${fixtureDigestMatch}\n`,
		);
	});

	// ── cross-language default resolution parity ─────────────────────────────

	it("resolves the phase-only default identically on both sides", () => {
		// Same fixture the Python `test_rag_config.py` case loads: `default_server:
		// B` (no rewrite capability) with the `design` phase declaring server `A`
		// (rewrite: true) + `source: docs`; `roles.coding` only declares `require`.
		const root = mkdtemp("mw-rag-parity-phase-only-");
		fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
		fs.copyFileSync(PHASE_ONLY_TARGET, path.join(root, ".agenticdoc", "target.yml"));
		process.env[ENV_RAG_SERVERS_FILE] = MACHINE_FIXTURE;
		const config = loadRagConfig(root);

		// The phase-declared server must survive `default_server: B` (D-102) and
		// the phase-level research rewrite default fires on A's capability.
		// `rewrite` must come from the resolver output, not from a literal.
		const resolved = resolveDefaults(config, "coding", "design");
		expect(resolved).toEqual({ server: "A", source: "docs", rewrite: true });

		// No phase -> the default server is still B and rewrite stays off, so the
		// fallback position is unchanged (VC-110).
		const fallback = resolveDefaults(config, "coding", "");
		expect(fallback.server).toBe("B");
		expect(fallback.rewrite).toBe(false);

		process.stdout.write(
			`[VERIFY] VC-111: server=${resolved.server} source=${resolved.source} rewrite=${resolved.rewrite}\n`,
		);
	});
});

// ── VC-305: skill.dir default/null fingerprint parity ───────────────────────

describe("RAG skill.dir fingerprint parity (VC-305)", () => {
	it.skipIf(!pythonAvailable)("keeps TS ragFingerprint byte-identical to Python for dir default/null/explicit", () => {
		const variants = [
			{ label: "default", skillLines: ["      cli_entry: scripts/cli.py"], expectedDir: null },
			{
				label: "null",
				skillLines: ["      dir: null", "      cli_entry: scripts/cli.py"],
				expectedDir: null,
			},
			{
				label: "explicit",
				skillLines: ["      dir: skills/x", "      cli_entry: scripts/cli.py"],
				expectedDir: "skills/x",
			},
		];
		const measured: string[] = [];
		for (const variant of variants) {
			const root = dirVariantRoot(variant.skillLines);
			const config = loadRagConfig(root);
			const parsedDir = config.servers.S.skill?.dir ?? null;
			expect(parsedDir).toBe(variant.expectedDir);
			const tsFingerprint = ragFingerprint(config);
			const pyFingerprint = pythonFingerprint(root);
			expect(tsFingerprint).toBe(pyFingerprint);
			measured.push(`dir=${variant.label} parsed=${String(parsedDir)} ts==py prefix=${tsFingerprint.slice(0, 12)}`);
		}
		expect(measured).toHaveLength(3);
		process.stdout.write(`[VERIFY] VC-305: ${measured.join(" | ")}\n`);
	});
});
