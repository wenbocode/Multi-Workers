/**
 * Autopilot config cross-language parity — the MAIN judge (mw-autopilot-verify-cli
 * T-07, design D-013, AC-006 / VC-006).
 *
 * The Python side (`autopilot/config.py`, T-01) owns the file-family schema; the
 * TS side (`autopilot/status-model.ts`, T-04) mirrors it for the read-only
 * console. This suite reads the SAME shared corpus
 * (`test/fixtures/autopilot-config-corpus.json`, T-07) and runs the real Python
 * module as a subprocess, so every conclusion is differential, never a
 * hand-copied constant:
 *
 *   P1 accept/reject + offending-field-name set identical per payload
 *   P2 `save_config` and `saveConfig` produce byte-identical files (sha256)
 *   P3 read-modify-write is byte-idempotent in BOTH directions
 *   P6 a one-key partial file yields the full 13-key shape on both sides
 *
 * Fail-closed (design D-013 / P-016): a missing interpreter or a failing
 * subprocess is a hard failure. There is deliberately no `skipIf` here — a
 * skipped case would be a hollow measurement.
 */

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterAll, describe, expect, it } from "vitest";
import { DEFAULT_CONFIG, readConfig, saveConfig } from "../../src/extensions/agent-team-loop/autopilot/status-model.ts";
import { resolveRagPython } from "../../src/extensions/agent-team-loop/rag/cli-bridge.ts";

const CORPUS_FILE = fileURLToPath(
	new URL("../../../multi-workers/test/fixtures/autopilot-config-corpus.json", import.meta.url),
);
/** `packages/multi-workers` — the Python ground-truth sources (precedent:
 * `rag-parity.test.ts:131`). */
const MULTI_WORKERS_DIR = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));

interface CorpusCase {
	id: string;
	categories: string[];
	payload_text: string;
	expected: { verdict: "accept" | "reject"; error_fields: string[] };
}
interface Corpus {
	schema: string;
	cases: CorpusCase[];
}

const CORPUS = JSON.parse(fs.readFileSync(CORPUS_FILE, "utf8")) as Corpus;
const KNOWN_FIELDS: string[] = Object.keys(DEFAULT_CONFIG);

/** Violating-field-name set from a validator message. Value rendering is
 * intentionally ignored (design D-013: `'yes'` vs `"yes"` does not count), so
 * this only harvests field identifiers plus the `unknown field(s):` list. */
function errorFields(message: string): string[] {
	const found = new Set<string>();
	for (const field of KNOWN_FIELDS) {
		if (new RegExp(`\\b${field}\\b`).test(message)) found.add(field);
	}
	const unknown = /unknown field\(s\): ([^;]+)/.exec(message);
	if (unknown) {
		for (const token of unknown[1].split(",")) {
			const trimmed = token.trim();
			if (trimmed.length > 0) found.add(trimmed);
		}
	}
	return [...found].sort();
}

/**
 * Python half of the measurement, run as a real subprocess. `mode=measure`
 * seeds each case's payload file then reads + re-saves it; `mode=crossread`
 * starts from a tree the TS side already wrote and only reads + re-saves, so
 * P3 can check byte idempotence in the TS -> Python direction too.
 */
const PY_HARNESS = [
	"import hashlib, json, pathlib, re, sys",
	"sys.path.insert(0, sys.argv[1])",
	"from autopilot import config",
	"corpus = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding='utf-8'))",
	"work = pathlib.Path(sys.argv[3])",
	"mode = sys.argv[4]",
	"known = list(config.DEFAULT_CONFIG)",
	"",
	"def error_fields(message):",
	"    found = {k for k in known if re.search(r'\\b' + re.escape(k) + r'\\b', message)}",
	"    match = re.search(r'unknown field\\(s\\): ([^;]+)', message)",
	"    if match:",
	"        for token in match.group(1).split(','):",
	"            token = token.strip()",
	"            if token:",
	"                found.add(token)",
	"    return sorted(found)",
	"",
	"cases = {}",
	"for index, case in enumerate(corpus['cases']):",
	"    root = work / ('%02d-%s' % (index, case['id']))",
	"    path = config.config_path(root)",
	"    if mode == 'measure':",
	"        path.parent.mkdir(parents=True, exist_ok=True)",
	"        path.write_text(case['payload_text'], encoding='utf-8')",
	"    if not path.exists():",
	"        raise SystemExit('missing payload file: %s' % path)",
	"    before = hashlib.sha256(path.read_bytes()).hexdigest()",
	"    try:",
	"        loaded = config.load_config(root)",
	"        record = {'verdict': 'accept', 'error_fields': []}",
	"    except config.ConfigError as exc:",
	"        loaded = None",
	"        record = {'verdict': 'reject', 'error_fields': error_fields(str(exc))}",
	"    if loaded is not None:",
	"        if len(loaded) != 13:",
	"            raise SystemExit('partial read did not yield 13 keys: %s' % case['id'])",
	"        record['keys'] = list(loaded.keys())",
	"        config.save_config(root, loaded)",
	"        record['before_sha256'] = before",
	"        record['after_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()",
	"    cases[case['id']] = record",
	"",
	"print('PARITY_JSON_BEGIN')",
	"print(json.dumps({'mode': mode, 'cases': cases}, ensure_ascii=False))",
	"print('PARITY_JSON_END')",
].join("\n");

interface PyCaseResult {
	verdict: "accept" | "reject";
	error_fields: string[];
	keys?: string[];
	before_sha256?: string;
	after_sha256?: string;
}

interface PyHarnessResult {
	mode: string;
	cases: Record<string, PyCaseResult>;
}

interface TsCaseResult {
	verdict: "accept" | "reject";
	errorFields: string[];
	keys: string[];
	sha256: string;
}

const tmpDirs: string[] = [];
afterAll(() => {
	for (const dir of tmpDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tmpDirs.push(dir);
	return dir;
}

function sha256File(file: string): string {
	return createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

function caseDir(workDir: string, index: number, id: string): string {
	return path.join(workDir, `${String(index).padStart(2, "0")}-${id}`);
}

function configFile(root: string): string {
	return path.join(root, ".agenticdoc", "_autopilot", "config.json");
}

/** Run the real Python module. Fails closed with stderr in the message. */
function runPythonHarness(workDir: string, mode: "measure" | "crossread"): PyHarnessResult {
	const result = spawnSync(resolveRagPython(), ["-c", PY_HARNESS, MULTI_WORKERS_DIR, CORPUS_FILE, workDir, mode], {
		encoding: "utf8",
		timeout: 30_000,
		env: process.env,
	});
	const stdout = result.stdout ?? "";
	const stderr = result.stderr ?? "";
	const begin = stdout.indexOf("PARITY_JSON_BEGIN");
	const end = stdout.indexOf("PARITY_JSON_END");
	if (result.status !== 0 || begin < 0 || end < 0) {
		throw new Error(
			`python config parity harness failed (mode=${mode}, status=${String(result.status)}): ` +
				`${stdout}\n${stderr}`,
		);
	}
	const text = stdout.slice(begin + "PARITY_JSON_BEGIN".length, end).trim();
	return JSON.parse(text) as PyHarnessResult;
}

/** TS half of the measurement: seed, read, re-save every case. */
function measureTs(workDir: string): Map<string, TsCaseResult> {
	const measured = new Map<string, TsCaseResult>();
	CORPUS.cases.forEach((testCase, index) => {
		const root = caseDir(workDir, index, testCase.id);
		const file = configFile(root);
		fs.mkdirSync(path.dirname(file), { recursive: true });
		fs.writeFileSync(file, testCase.payload_text, "utf8");
		const read = readConfig(root);
		if (!read.ok) {
			measured.set(testCase.id, {
				verdict: "reject",
				errorFields: errorFields(read.error),
				keys: [],
				sha256: "",
			});
			return;
		}
		const saved = saveConfig(root, read.config);
		if (!saved.ok) throw new Error(`TS saveConfig refused ${testCase.id}: ${saved.error}`);
		measured.set(testCase.id, {
			verdict: "accept",
			errorFields: [],
			keys: Object.keys(read.config),
			sha256: sha256File(file),
		});
	});
	return measured;
}

let cached: { py: PyHarnessResult; ts: Map<string, TsCaseResult>; pyDir: string; tsDir: string } | undefined;

/** Both halves measured exactly once and shared by P1/P2/P3/P6. */
function measure(): { py: PyHarnessResult; ts: Map<string, TsCaseResult>; pyDir: string; tsDir: string } {
	if (cached !== undefined) return cached;
	const pyDir = mkdtemp("mw-apcfg-py-");
	const tsDir = mkdtemp("mw-apcfg-ts-");
	const ts = measureTs(tsDir);
	const py = runPythonHarness(pyDir, "measure");
	cached = { py, ts, pyDir, tsDir };
	return cached;
}

/** P6 candidate set: payloads that parse to a JSON object with exactly one key. */
function singleKeyCases(): { testCase: CorpusCase; key: string }[] {
	const out: { testCase: CorpusCase; key: string }[] = [];
	for (const testCase of CORPUS.cases) {
		if (testCase.expected.verdict !== "accept") continue;
		let parsed: unknown;
		try {
			parsed = JSON.parse(testCase.payload_text);
		} catch {
			continue;
		}
		if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) continue;
		const keys = Object.keys(parsed);
		if (keys.length === 1) out.push({ testCase, key: keys[0] });
	}
	return out;
}

describe("autopilot config cross-language parity (AC-006 / VC-006)", () => {
	it("P1: both sides reach the same accept/reject verdict and offending-field set", () => {
		const { py, ts } = measure();
		let compared = 0;
		for (const testCase of CORPUS.cases) {
			const pyCase = py.cases[testCase.id];
			const tsCase = ts.get(testCase.id);
			expect(pyCase, `python harness missing ${testCase.id}`).toBeDefined();
			expect(tsCase, `ts measurement missing ${testCase.id}`).toBeDefined();
			if (pyCase === undefined || tsCase === undefined) continue;
			// The corpus expectation is asserted too, so both sides drifting the
			// same way cannot hide behind the differential.
			expect(tsCase.verdict, `${testCase.id}: ts vs corpus`).toBe(testCase.expected.verdict);
			expect(pyCase.verdict, `${testCase.id}: py vs corpus`).toBe(testCase.expected.verdict);
			expect(pyCase.verdict, `${testCase.id}: py vs ts`).toBe(tsCase.verdict);
			if (testCase.expected.verdict === "reject") {
				expect(tsCase.errorFields, `${testCase.id}: ts field set`).toEqual(testCase.expected.error_fields);
				expect(pyCase.error_fields, `${testCase.id}: py field set`).toEqual(testCase.expected.error_fields);
				expect(pyCase.error_fields, `${testCase.id}: py vs ts field set`).toEqual(tsCase.errorFields);
			}
			compared += 1;
		}
		expect(compared).toBe(CORPUS.cases.length);
		process.stdout.write(`[VERIFY] P1: crosslang_verdict_match=${compared}/${CORPUS.cases.length}\n`);
	});

	it("P2: save_config and saveConfig write byte-identical files (sha256)", () => {
		const { py, ts } = measure();
		let compared = 0;
		for (const testCase of CORPUS.cases) {
			const pyCase = py.cases[testCase.id];
			const tsCase = ts.get(testCase.id);
			if (pyCase?.verdict !== "accept" || tsCase?.verdict !== "accept") continue;
			expect(pyCase.after_sha256, `${testCase.id}: python canonical sha`).toBeDefined();
			expect(tsCase.sha256, `${testCase.id}: ts canonical sha`).toBe(pyCase.after_sha256);
			compared += 1;
		}
		expect(compared).toBeGreaterThanOrEqual(31);
		process.stdout.write(`[VERIFY] P2: canonical_sha_match=${compared} sha256_equal=true\n`);
	});

	it("P3: read-modify-write is byte-idempotent in both directions", () => {
		const { py, ts, pyDir, tsDir } = measure();
		let pyToTs = 0;
		let tsToPy = 0;
		for (let index = 0; index < CORPUS.cases.length; index += 1) {
			const testCase = CORPUS.cases[index];
			const pyCase = py.cases[testCase.id];
			const tsCase = ts.get(testCase.id);
			if (pyCase?.verdict !== "accept" || tsCase?.verdict !== "accept") continue;

			// Python wrote -> TS reads and re-writes: the file must not move.
			const pyRoot = caseDir(pyDir, index, testCase.id);
			const pyFile = configFile(pyRoot);
			const res = readConfig(pyRoot);
			expect(res.ok, `${testCase.id}: ts must read the python file`).toBe(true);
			if (res.ok) {
				const saved = saveConfig(pyRoot, res.config);
				expect(saved.ok, `${testCase.id}: ts re-save`).toBe(true);
				expect(sha256File(pyFile), `${testCase.id}: py -> ts bytes`).toBe(pyCase.after_sha256);
				pyToTs += 1;
			}
		}
		// TS wrote -> Python reads and re-writes. One extra subprocess over the
		// tree the TS half produced.
		const cross = runPythonHarness(tsDir, "crossread");
		for (const testCase of CORPUS.cases) {
			const crossCase = cross.cases[testCase.id];
			const tsCase = ts.get(testCase.id);
			if (tsCase?.verdict !== "accept") continue;
			expect(crossCase?.verdict, `${testCase.id}: python must read the ts file`).toBe("accept");
			expect(crossCase?.before_sha256, `${testCase.id}: ts -> py before`).toBe(tsCase.sha256);
			expect(crossCase?.after_sha256, `${testCase.id}: ts -> py after`).toBe(crossCase?.before_sha256);
			tsToPy += 1;
		}
		expect(pyToTs).toBeGreaterThanOrEqual(31);
		expect(tsToPy).toBe(pyToTs);
		process.stdout.write(`[VERIFY] P3: py_to_ts_idempotent=${pyToTs} ts_to_py_idempotent=${tsToPy}\n`);
	});

	it("P6: a one-key partial file yields the full 13-key shape on both sides", () => {
		const { py, ts } = measure();
		const expectedKeys = Object.keys(DEFAULT_CONFIG);
		const partials = singleKeyCases();
		const covered = new Set<string>();
		for (const { testCase, key } of partials) {
			const pyCase = py.cases[testCase.id];
			const tsCase = ts.get(testCase.id);
			expect(pyCase?.verdict, `${testCase.id}: py`).toBe("accept");
			expect(tsCase?.verdict, `${testCase.id}: ts`).toBe("accept");
			expect(tsCase?.keys.length, `${testCase.id}: ts key count`).toBe(13);
			expect(pyCase?.keys?.length, `${testCase.id}: py key count`).toBe(13);
			expect([...(tsCase?.keys ?? [])].sort(), `${testCase.id}: ts key set`).toEqual([...expectedKeys].sort());
			expect([...(pyCase?.keys ?? [])].sort(), `${testCase.id}: py key set`).toEqual([...expectedKeys].sort());
			covered.add(key);
		}
		// Every one of the 13 fields must be exercised as the sole key.
		expect([...covered].sort()).toEqual([...expectedKeys].sort());
		process.stdout.write(
			`[VERIFY] P6: partial_single_key=${partials.length} both_13_keys=true fields_covered=${covered.size}\n`,
		);
	});
});
