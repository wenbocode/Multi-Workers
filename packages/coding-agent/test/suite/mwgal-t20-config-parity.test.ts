/**
 * Optional autopilot config key parity (T-20 closeout) — the regression guard
 * for the `envelope_fallback` break that survived the previous key's closeout.
 *
 * Incident (mw-dispatch-card-gate commit `b65380d1b`): the Python side added
 * `ENVELOPE_FALLBACK_KEY = "envelope_fallback"` to `_BOOL_FIELDS` (config.py
 * :112-113) while deliberately keeping it OUT of the frozen 20-key
 * `DEFAULT_CONFIG` (config.py :61-65, allowed in `validate_config` at :151,
 * read by `envelope_fallback_enabled` at :230-241). The TS mirror was not
 * updated, so the P5 registry lock stayed red from that commit on and
 * `validateConfigData` classified a legitimate Python-accepted key as
 * `unknown field(s)`. `npm run check` does not run tests, so the closeout
 * missed it.
 *
 * This file pins the *optional* key category rather than the two literals:
 *   - a registered-but-optional key must be a member of `BOOL_FIELDS` and must
 *     NOT be a `DEFAULT_CONFIG` key (Python truth, checked differentially);
 *   - `validateConfigData` must accept the optional key with the same verdict
 *     as `config.validate_config`, and must still refuse anything else;
 *   - `readConfig` / `saveConfig` must keep the canonical 20-key shape, so the
 *     optional key never leaks into the materialized config (Python's
 *     effective view drops it too).
 *
 * Fail-closed like the other config suites: a missing interpreter or a failing
 * subprocess throws with stderr instead of skipping.
 */

import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterAll, describe, expect, it } from "vitest";
import {
	BOOL_FIELDS,
	DEFAULT_CONFIG,
	OPTIONAL_CONFIG_KEYS,
	readConfig,
	saveConfig,
	validateConfigData,
} from "../../src/extensions/agent-team-loop/autopilot/status-model.ts";
import { resolveRagPython } from "../../src/extensions/agent-team-loop/rag/cli-bridge.ts";

const MULTI_WORKERS_DIR = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));

/** Python registry dump: the frozen schema plus the optional-key marker. */
const PY_REGISTRY_DUMP = [
	"import json, sys",
	"sys.path.insert(0, sys.argv[1])",
	"from autopilot import config",
	"print('P5_JSON_BEGIN')",
	"print(json.dumps({",
	"    'keys': list(config.DEFAULT_CONFIG.keys()),",
	"    'bool_fields': list(config._BOOL_FIELDS),",
	"    'envelope_fallback_key': config.ENVELOPE_FALLBACK_KEY,",
	"}, ensure_ascii=False))",
	"print('P5_JSON_END')",
].join("\n");

interface PyRegistry {
	keys: string[];
	bool_fields: string[];
	envelope_fallback_key: string;
}

function pythonRegistry(): PyRegistry {
	const result = spawnSync(resolveRagPython(), ["-c", PY_REGISTRY_DUMP, MULTI_WORKERS_DIR], {
		encoding: "utf8",
		timeout: 30_000,
		env: process.env,
	});
	const stdout = result.stdout ?? "";
	const stderr = result.stderr ?? "";
	const begin = stdout.indexOf("P5_JSON_BEGIN");
	const end = stdout.indexOf("P5_JSON_END");
	if (result.status !== 0 || begin < 0 || end < 0) {
		throw new Error(`python registry dump failed (status=${String(result.status)}): ${stdout}\n${stderr}`);
	}
	return JSON.parse(stdout.slice(begin + "P5_JSON_BEGIN".length, end).trim()) as PyRegistry;
}

/** Differential verdict harness: `config.validate_config(payload)`. */
const PY_VERDICT_HARNESS = [
	"import json, sys",
	"sys.path.insert(0, sys.argv[1])",
	"from autopilot import config",
	"payload = json.loads(sys.argv[2])",
	"try:",
	"    config.validate_config(payload)",
	"    print('P5V_BEGIN'); print(json.dumps({'verdict': 'accept', 'error': ''})); print('P5V_END')",
	"except config.ConfigError as exc:",
	"    print('P5V_BEGIN'); print(json.dumps({'verdict': 'reject', 'error': str(exc)})); print('P5V_END')",
].join("\n");

interface PyVerdict {
	verdict: "accept" | "reject";
	error: string;
}

function pythonVerdict(payload: unknown): PyVerdict {
	const result = spawnSync(
		resolveRagPython(),
		["-c", PY_VERDICT_HARNESS, MULTI_WORKERS_DIR, JSON.stringify(payload)],
		{ encoding: "utf8", timeout: 30_000, env: process.env },
	);
	const stdout = result.stdout ?? "";
	const stderr = result.stderr ?? "";
	const begin = stdout.indexOf("P5V_BEGIN");
	const end = stdout.indexOf("P5V_END");
	if (result.status !== 0 || begin < 0 || end < 0) {
		throw new Error(`python verdict harness failed (status=${String(result.status)}): ${stdout}\n${stderr}`);
	}
	return JSON.parse(stdout.slice(begin + "P5V_BEGIN".length, end).trim()) as PyVerdict;
}

const tmpDirs: string[] = [];
afterAll(() => {
	for (const dir of tmpDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mwgal-t20-"));
	tmpDirs.push(dir);
	return dir;
}

function writeRawConfig(root: string, body: string): string {
	const dir = path.join(root, ".agenticdoc", "_autopilot");
	fs.mkdirSync(dir, { recursive: true });
	const file = path.join(dir, "config.json");
	fs.writeFileSync(file, `${body}\n`, "utf8");
	return file;
}

describe("optional autopilot config key parity (T-20)", () => {
	it("registers the optional key in BOOL_FIELDS and keeps it out of DEFAULT_CONFIG", () => {
		const py = pythonRegistry();
		const optionalPy = py.bool_fields.filter((field) => !py.keys.includes(field));

		// Python truth: exactly one optional key, and it is the envelope hatch.
		expect(optionalPy).toEqual([py.envelope_fallback_key]);
		expect(py.keys).toHaveLength(20);
		expect(py.bool_fields).toHaveLength(4);

		// TS truth: the derived optional registry matches Python item-for-item.
		expect([...OPTIONAL_CONFIG_KEYS].sort()).toEqual([...optionalPy].sort());
		for (const field of OPTIONAL_CONFIG_KEYS) {
			expect([...BOOL_FIELDS], `${field}: registered as a bool`).toContain(field);
			expect(Object.keys(DEFAULT_CONFIG), `${field}: outside the 20-key schema`).not.toContain(field);
			expect(
				(DEFAULT_CONFIG as unknown as Record<string, unknown>)[field],
				`${field}: no materialized default`,
			).toBeUndefined();
		}

		process.stdout.write(
			`[VERIFY] T-20: defaults=${py.keys.length} bool=${py.bool_fields.length} ` +
				`optional=${optionalPy.join(",")} ts_optional=${[...OPTIONAL_CONFIG_KEYS].join(",")}\n`,
		);
	});

	it("validateConfigData reaches the same verdict as Python validate_config for the optional key", () => {
		const good: unknown[] = [{ envelope_fallback: true }, { envelope_fallback: false }];
		const bad: unknown[] = [{ envelope_fallback: 1 }, { envelope_fallback: "yes" }, { envelope_fallback: null }];

		for (const payload of good) {
			expect(validateConfigData(payload), `ts accepts ${JSON.stringify(payload)}`).toEqual([]);
			expect(pythonVerdict(payload).verdict, `py accepts ${JSON.stringify(payload)}`).toBe("accept");
		}
		for (const payload of bad) {
			const errors = validateConfigData(payload);
			expect(errors.length, `ts rejects ${JSON.stringify(payload)}`).toBeGreaterThan(0);
			expect(errors.join("; "), `ts names envelope_fallback for ${JSON.stringify(payload)}`).toContain(
				"envelope_fallback: expected true/false",
			);
			const py = pythonVerdict(payload);
			expect(py.verdict, `py rejects ${JSON.stringify(payload)}`).toBe("reject");
			expect(py.error, `py names envelope_fallback for ${JSON.stringify(payload)}`).toContain("envelope_fallback");
		}

		// The allowance is exactly the registered optional key: an unregistered
		// key is still refused on BOTH sides (no wildcard admission).
		const bogus = { envelope_fallback_typo: true };
		expect(validateConfigData(bogus).join("; ")).toContain("unknown field(s): envelope_fallback_typo");
		expect(pythonVerdict(bogus).verdict).toBe("reject");

		process.stdout.write(`[VERIFY] T-20: optional_key_verdicts_mirror_python=${good.length + bad.length + 1}\n`);
	});

	it("readConfig accepts the optional key and still yields the canonical 20-key merged shape", () => {
		const root = mkdtemp();
		writeRawConfig(root, '{"envelope_fallback": true}');
		const read = readConfig(root);
		expect(read.ok).toBe(true);
		if (read.ok) {
			expect(Object.keys(read.config), "merged view stays 20 keys").toHaveLength(20);
			expect(Object.keys(read.config)).not.toContain("envelope_fallback");
			expect(read.config.enabled).toBe(false); // unset fields keep defaults
		}

		// A present-but-unregistered key is still refused, so accepting the
		// optional key did not loosen the unknown-field guard.
		const bogusRoot = mkdtemp();
		writeRawConfig(bogusRoot, '{"envelope_fallback_typo": true}');
		const bogusRead = readConfig(bogusRoot);
		expect(bogusRead.ok).toBe(false);
		if (!bogusRead.ok) expect(bogusRead.error).toContain("unknown field(s): envelope_fallback_typo");

		process.stdout.write(`[VERIFY] T-20: optional_key_accepted=true merged_keys=20 unknown_still_refused=true\n`);
	});

	it("saveConfig never materializes the optional key (canonical 20-key write)", () => {
		const root = mkdtemp();
		const saved = saveConfig(root, { ...DEFAULT_CONFIG });
		expect(saved.ok).toBe(true);
		const file = path.join(root, ".agenticdoc", "_autopilot", "config.json");
		const written = JSON.parse(fs.readFileSync(file, "utf8")) as Record<string, unknown>;
		expect(Object.keys(written), "written config stays 20 keys").toHaveLength(20);
		expect(Object.keys(written)).not.toContain("envelope_fallback");
		expect(Object.keys(written)).toEqual(Object.keys(DEFAULT_CONFIG));

		process.stdout.write(
			`[VERIFY] T-20: canonical_write_keys=${Object.keys(written).length} optional_materialized=false\n`,
		);
	});
});
