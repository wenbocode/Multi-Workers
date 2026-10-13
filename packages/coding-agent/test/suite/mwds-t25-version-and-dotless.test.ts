/**
 * mwds-t25-version-and-dotless.test.ts — T-25 (key mw-dispatch-card-gate, wave 16):
 * two post-cutover runtime defects measured on the live service.
 *
 * C-31 (producer version is always `0.0.0`): `config.ts` read
 * `pkg.version || "0.0.0"` at runtime, but a bundled extension cannot resolve
 * `packages/coding-agent/package.json` (its `import.meta.url` points at the
 * install dir). The emitted `envelope_producer: agent-team-loop-pm@0.0.0` line
 * made the T-14 producer-version skew check incomparable on the TS dispatch
 * path. Fix: the bundle build injects the real version with esbuild `define`
 * (`mw.py::_build_bundle` / `build-extension.sh`) and `config.ts` prefers it.
 *
 * dotless漏红: the T-21 shape whitelist refuses a separator-bearing token whose
 * basename has no `.`; a real extensionless file (`scripts/deploy`) was thus
 * dropped from `declared`, and a genuine out-of-scope write stayed green. Fix:
 * after the shape gate, arbitrate by existence — an existing file/directory is
 * a declaration (still counted in `collectMalformedCandidates`), a nonexistent
 * token (`host/pid`) keeps the old behaviour.
 *
 * Verification of the build injection is the esbuild probe below: the same
 * `define` mw.py passes is applied to a temporary config.ts bundle whose
 * `PI_PACKAGE_DIR` has no package.json. Without the define it reproduces C-31
 * (`0.0.0`); with it the bundle carries the real version. The full-bundle
 * `_build_bundle(out=<tmp>)` assertion lives in the Python sibling
 * `packages/multi-workers/test_mwds_t25_version_semantics.py` (no
 * `build --install`, the tracked dist artifact is never touched).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import * as esbuild from "esbuild";
import { afterEach, describe, expect, it } from "vitest";
import { VERSION } from "../../src/config.ts";
import {
	DISPATCH_PRODUCER_ID,
	ENVELOPE_PRODUCER_KEY,
	envelopeProducerIdentity,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { collectMalformedCandidates, diffLedger } from "../../src/extensions/agent-team-loop/shared/change-ledger.ts";

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));
const PKG_ROOT = path.resolve(TEST_DIR, "../..");
const REPO_ROOT = path.resolve(TEST_DIR, "../../../..");
const CONFIG_TS = path.join(PKG_ROOT, "src", "config.ts");
const PACKAGE_VERSION: string = (
	JSON.parse(fs.readFileSync(path.join(PKG_ROOT, "package.json"), "utf8")) as { version: string }
).version;

const tempDirs: string[] = [];

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function report(body: readonly string[]): string {
	return ["## 结论", "", "done", "", "## 改动清单", "", ...body, "", "## 残留与未验证", "", "none"].join("\n");
}

function trace(recorded: readonly string[]): string {
	return recorded.map((file) => `[WRITE_FILE] path=${file}`).join("\n");
}

/** A throwaway tree with `scripts/deploy` (extensionless, separator-bearing). */
function tempRepoWithDeploy(): string {
	const root = mkdtemp("mwds-t25-repo-");
	fs.mkdirSync(path.join(root, "scripts"), { recursive: true });
	fs.writeFileSync(path.join(root, "scripts", "deploy"), "#!/bin/sh\necho deploy\n", "utf8");
	return root;
}

// ── C-31: build-time version injection ───────────────────────────────────────

describe("T-25 requirement 1 — bundle carries the real version (C-31)", () => {
	it("the source-tree VERSION and the identity line are a real version, not 0.0.0", () => {
		expect(VERSION).toBe(PACKAGE_VERSION);
		expect(VERSION).toMatch(/^\d+\.\d+\.\d+/);
		expect(VERSION).not.toBe("0.0.0");
		const identity = envelopeProducerIdentity();
		expect(identity).toBe(`${DISPATCH_PRODUCER_ID}@${VERSION}`);
		expect(ENVELOPE_PRODUCER_KEY).toBe("envelope_producer");
		console.log(`[VERIFY] T25-1 source VERSION=${VERSION} identity=${identity}`);
	});

	/** Build a temporary config.ts bundle and read its `VERSION` back. The
	 * package.json lookup is forced into an empty dir, so the runtime `pkg`
	 * read is exactly the C-31 failure mode (present in the install dir). */
	async function builtVersion(define: boolean): Promise<string> {
		const dir = mkdtemp("mwds-t25-define-");
		const emptyPkgDir = path.join(dir, "no-package-json");
		fs.mkdirSync(emptyPkgDir, { recursive: true });
		const entry = path.join(dir, "entry.ts");
		const out = path.join(dir, "entry.mjs");
		fs.writeFileSync(entry, `export { VERSION } from ${JSON.stringify(CONFIG_TS.replace(/\\/g, "/"))};\n`, "utf8");
		await esbuild.build({
			entryPoints: [entry],
			bundle: true,
			outfile: out,
			platform: "node",
			format: "esm",
			target: "node18",
			external: ["node:*"],
			define: define ? { __PI_CODING_AGENT_VERSION__: JSON.stringify(PACKAGE_VERSION) } : {},
			logLevel: "silent",
		});
		const previous = process.env.PI_PACKAGE_DIR;
		process.env.PI_PACKAGE_DIR = emptyPkgDir;
		try {
			const mod = (await import(
				/* @vite-ignore */ `${pathToFileURL(out).href}?case=${define ? "define" : "runtime"}`
			)) as { VERSION: string };
			return mod.VERSION;
		} finally {
			if (previous === undefined) delete process.env.PI_PACKAGE_DIR;
			else process.env.PI_PACKAGE_DIR = previous;
		}
	}

	it("without the define a bundled copy still falls back to 0.0.0 (the executed C-31 bug)", async () => {
		await expect(builtVersion(false)).resolves.toBe("0.0.0");
		console.log("[VERIFY] T25-1 bundle_without_define=0.0.0 (C-31 reproduced)");
	});

	it("with the esbuild define the bundled copy carries the package.json version", async () => {
		const injected = await builtVersion(true);
		console.log(`[VERIFY] T25-1 bundle_with_define=${injected} expected=${PACKAGE_VERSION}`);
		expect(injected).toBe(PACKAGE_VERSION);
		expect(injected).not.toBe("0.0.0");
	});

	it("mw.py injects the same define into the real bundle build", () => {
		// Source contract: the build path must pass packages/coding-agent's
		// version through the same identifier config.ts reads.
		const mwSource = fs.readFileSync(path.join(REPO_ROOT, "packages", "multi-workers", "mw.py"), "utf8");
		expect(mwSource).toContain("__PI_CODING_AGENT_VERSION__");
		expect(mwSource).toContain('env["MW_VERSION"]');
		const configSource = fs.readFileSync(CONFIG_TS, "utf8");
		expect(configSource).toContain("declare const __PI_CODING_AGENT_VERSION__");
		console.log("[VERIFY] T25-1 mw_define_wired=true config_prefers_define=true");
	});
});

// ── dotless existence arbitration ────────────────────────────────────────────

describe("T-25 requirement 3/4① — dotless `scripts/deploy`", () => {
	const DECLARED = "scripts/deploy";

	it("with a matching trace event: declared, and not in extra", () => {
		const root = tempRepoWithDeploy();
		const text = report([`- ${DECLARED} — 无扩展名部署脚本`]);
		const ledger = diffLedger(text, trace([DECLARED]), { projectRoot: root });
		const malformed = collectMalformedCandidates(text);
		console.log(
			`[VERIFY] T25-① recorded declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}] malformed=[${malformed.join(",")}]`,
		);
		expect(ledger.declared).toEqual([DECLARED]);
		expect(ledger.extra).toEqual([]);
		// Still counted in the warn-only malformed bucket (shape signal kept).
		expect(malformed).toContain(DECLARED);
	});

	it("without a matching trace event: declared and RED (extra names it)", () => {
		const root = tempRepoWithDeploy();
		const text = report([`- ${DECLARED} — 无扩展名部署脚本`]);
		// Non-empty trace so this is not the "zero events ⇒ unjudgeable" branch.
		const ledger = diffLedger(text, trace(["packages/coding-agent/src/other.ts"]), { projectRoot: root });
		const malformed = collectMalformedCandidates(text);
		console.log(
			`[VERIFY] T25-①-miss declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}] malformed=[${malformed.join(",")}]`,
		);
		expect(ledger.declared).toEqual([DECLARED]);
		expect(ledger.extra).toEqual([DECLARED]);
		expect(ledger.unjudgeable).toBe(false);
		expect(malformed).toContain(DECLARED);
	});

	it("a nonexistent dotless token keeps the status quo (not declared)", () => {
		const root = tempRepoWithDeploy();
		const text = report(["- scripts/nope — 不存在的无扩展名脚本"]);
		const ledger = diffLedger(text, trace(["packages/coding-agent/src/other.ts"]), { projectRoot: root });
		console.log(
			`[VERIFY] T25-3 nonexistent declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}]`,
		);
		expect(ledger.declared).toEqual([]);
		expect(ledger.extra).toEqual([]);
		expect(collectMalformedCandidates(text)).toContain("scripts/nope");
	});

	it("negation still wins over the existence arbitration", () => {
		const root = tempRepoWithDeploy();
		const text = report([`- 未改 ${DECLARED} — 只读审查`]);
		const ledger = diffLedger(text, trace(["packages/coding-agent/src/other.ts"]), { projectRoot: root });
		console.log(`[VERIFY] T25-3 negated_existing declared=[${ledger.declared.join(",")}]`);
		expect(ledger.declared).toEqual([]);
		expect(ledger.extra).toEqual([]);
	});

	it("a real directory form is arbitrated too (file OR directory)", () => {
		const root = tempRepoWithDeploy();
		fs.mkdirSync(path.join(root, "tools", "lint"), { recursive: true });
		const ledger = diffLedger(report(["- tools/lint — 目录"]), trace(["x.ts"]), { projectRoot: root });
		console.log(`[VERIFY] T25-3 dir declared=[${ledger.declared.join(",")}]`);
		expect(ledger.declared).toEqual(["tools/lint"]);
	});
});

describe("T-25 requirement 4② — the shape judgement is not relaxed", () => {
	it("English word pairs (`host/pid`, `notice/refusal`) are still not declarations", () => {
		const root = tempRepoWithDeploy();
		const text = report(["- host/pid — 形态残留", "- notice/refusal — 形态残留"]);
		const ledger = diffLedger(text, trace(["packages/coding-agent/src/other.ts"]), { projectRoot: root });
		const malformed = collectMalformedCandidates(text);
		console.log(`[VERIFY] T25-② declared=[${ledger.declared.join(",")}] malformed=[${malformed.join(",")}]`);
		expect(ledger.declared).toEqual([]);
		expect(ledger.extra).toEqual([]);
		expect(malformed).toContain("host/pid");
		expect(malformed).toContain("notice/refusal");
	});

	it("globs, ADS and full-width tokens stay malformed, never declarations", () => {
		const root = tempRepoWithDeploy();
		const text = report(["- src/** — glob", "- test/extensions/** — glob", "- （仅金样本/期望重基线）"]);
		const ledger = diffLedger(text, trace(["packages/coding-agent/src/other.ts"]), { projectRoot: root });
		expect(ledger.declared).toEqual([]);
		const malformed = collectMalformedCandidates(text);
		for (const token of ["src/**", "test/extensions/**", "（仅金样本/期望重基线）"]) {
			expect(malformed).toContain(token);
		}
		console.log(`[VERIFY] T25-② residual declared=0 malformed=[${malformed.join(",")}]`);
	});
});

// ── requirement 4③: real corpora stay green ──────────────────────────────────

const WORKERS_DIR = path.join(REPO_ROOT, ".agenticdoc", "mw-dispatch-card-gate", "workers");
const WORKER_ID = "mwd-t25-version-and-dotless";
const TASK_MD = path.join(WORKERS_DIR, WORKER_ID, "task.md");

describe("T-25 requirement 4③ — real corpora stay green", () => {
	it("T-18 / T-19 real reports keep extra=[] with the existence arbitration on", () => {
		const rows: Array<{ worker: string; extra: string[]; declared: string[] }> = [];
		for (const worker of ["mwd-t18-ts-producer-identity", "mwd-t19-orphan-ownership"]) {
			const dir = path.join(WORKERS_DIR, worker);
			const reportPath = path.join(dir, "report.md");
			const tracePath = path.join(dir, "trace.log");
			if (!fs.existsSync(reportPath) || !fs.existsSync(tracePath)) continue;
			// Explicit repo root: the production default is the worker cwd.
			const ledger = diffLedger(fs.readFileSync(reportPath, "utf8"), fs.readFileSync(tracePath, "utf8"), {
				projectRoot: REPO_ROOT,
			});
			rows.push({ worker, extra: ledger.extra, declared: ledger.declared });
		}
		expect(rows.length).toBeGreaterThanOrEqual(2);
		for (const row of rows) {
			console.log(`[VERIFY] T25-③ ${row.worker} declared=${row.declared.length} extra=[${row.extra.join(",")}]`);
			expect(row.extra).toEqual([]);
		}
	});

	it("this card's task.md 写入禁止面 segment declares nothing", () => {
		if (!fs.existsSync(TASK_MD)) {
			console.log("[VERIFY] T25-③ task.md unavailable — skipped");
			return;
		}
		const taskText = fs.readFileSync(TASK_MD, "utf8");
		const line = taskText.split(/\r?\n/).find((l) => l.includes("写入禁止面：")) ?? "";
		expect(line).not.toBe("");
		const segment = line.slice(line.indexOf("写入禁止面"));
		const ledger = diffLedger(report([segment]), trace(["packages/coding-agent/src/other.ts"]), {
			projectRoot: REPO_ROOT,
		});
		console.log(
			`[VERIFY] T25-③ forbidden_segment declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}]`,
		);
		expect(ledger.declared).toEqual([]);
		expect(ledger.extra).toEqual([]);
	});
});
