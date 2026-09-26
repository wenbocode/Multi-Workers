/**
 * Autopilot config corpus integrity (P4) + new-key mirror (P5) —
 * mw-autopilot-verify-cli T-07, design D-013, AC-006 / VC-006.
 *
 * P4 freezes the shared corpus the parity suite consumes: one sha256 + one case
 * count + a category-coverage assertion over the D1-D6 historical divergences.
 * Without it either side could quietly shrink the corpus until the parity suite
 * goes green (P-016: no hollow cases).
 *
 * P5 spawns the real Python module and compares the four registry tables and the
 * 13-key defaults byte-for-byte (key set, key ORDER, default values, JSON types,
 * and integer ranges) against the TS mirror in `status-model.ts`.
 *
 * Fail-closed: a missing interpreter or a failing subprocess throws with stderr.
 */

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
	BOOL_FIELDS,
	DEFAULT_CONFIG,
	INT_RANGES,
	LIST_FIELDS,
	STR_FIELDS,
} from "../../src/extensions/agent-team-loop/autopilot/status-model.ts";
import { resolveRagPython } from "../../src/extensions/agent-team-loop/rag/cli-bridge.ts";

const CORPUS_FILE = fileURLToPath(
	new URL("../../../multi-workers/test/fixtures/autopilot-config-corpus.json", import.meta.url),
);
const MULTI_WORKERS_DIR = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));

/** Frozen by T-07; any edit to the corpus must be a deliberate re-freeze. */
const FROZEN_CORPUS_SHA256 = "951987eaf2abebfa256365ed6642ce1ae0b077a2a6a6c18b4f974729c7dc594d";
const FROZEN_CORPUS_COUNT = 53;

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
const PAYLOADS = CORPUS.cases.map((testCase) => testCase.payload_text);
const IDS = new Set(CORPUS.cases.map((testCase) => testCase.id));

/** Python registry dump for P5. */
const PY_REGISTRY_DUMP = [
	"import json, sys",
	"sys.path.insert(0, sys.argv[1])",
	"from autopilot import config",
	"print('P5_JSON_BEGIN')",
	"print(json.dumps({",
	"    'keys': list(config.DEFAULT_CONFIG.keys()),",
	"    'defaults': config.DEFAULT_CONFIG,",
	"    'bool_fields': list(config._BOOL_FIELDS),",
	"    'list_fields': list(config._LIST_FIELDS),",
	"    'string_fields': list(config._STRING_FIELDS),",
	"    'int_ranges': {k: list(v) for k, v in config._INT_RANGES.items()},",
	"}, ensure_ascii=False))",
	"print('P5_JSON_END')",
].join("\n");

interface PyRegistryDump {
	keys: string[];
	defaults: Record<string, unknown>;
	bool_fields: string[];
	list_fields: string[];
	string_fields: string[];
	int_ranges: Record<string, (number | null)[]>;
}

function pythonRegistryDump(): PyRegistryDump {
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
	return JSON.parse(stdout.slice(begin + "P5_JSON_BEGIN".length, end).trim()) as PyRegistryDump;
}

describe("autopilot config corpus integrity (P4)", () => {
	it("freezes the shared corpus sha256, case count and D1-D6 coverage", () => {
		const digest = createHash("sha256").update(fs.readFileSync(CORPUS_FILE)).digest("hex");
		expect(digest, "corpus sha256 drifted; re-freeze deliberately").toBe(FROZEN_CORPUS_SHA256);
		expect(CORPUS.cases.length).toBe(FROZEN_CORPUS_COUNT);
		expect(CORPUS.schema).toBe("mw-autopilot-config-corpus/v1");

		// D1-D6 historical divergence classes must all be represented.
		const categories = new Set<string>();
		for (const testCase of CORPUS.cases) for (const category of testCase.categories) categories.add(category);
		for (const category of ["D1", "D2", "D3", "D4", "D5", "D6"]) {
			expect(categories.has(category), `corpus must cover ${category}`).toBe(true);
		}

		// Concrete payloads the contract names explicitly.
		const has = (text: string): boolean => PAYLOADS.some((payload) => payload.includes(text));
		expect(has("4.0"), "4.0 payload").toBe(true);
		expect(has("4.00"), "4.00 payload").toBe(true);
		expect(has("1e2"), "1e2 payload").toBe(true);
		expect(has("-0.0"), "-0.0 payload").toBe(true);
		expect(has("4.5"), "4.5 payload").toBe(true);
		expect(has('"4"'), '"4" string payload').toBe(true);
		expect(has('""'), "empty-string payload").toBe(true);
		expect(has("9007199254740992"), "2**53 payload").toBe(true);
		expect(has("9007199254740991"), "2**53-1 payload").toBe(true);
		// Non-ASCII payload (raw UTF-8, not \uXXXX only).
		expect(
			PAYLOADS.some((payload) => /[\u0080-\u{10ffff}]/u.test(payload)),
			"non-ASCII payload",
		).toBe(true);
		// Structural classes: unknown key, partial file, bool-as-int.
		expect(IDS.has("unknown-key")).toBe(true);
		expect(IDS.has("int-from-bool")).toBe(true);
		expect(IDS.has("partial-single")).toBe(true);
		const partials = CORPUS.cases.filter((testCase) => {
			let parsed: unknown;
			try {
				parsed = JSON.parse(testCase.payload_text);
			} catch {
				return false;
			}
			if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return false;
			const count = Object.keys(parsed).length;
			return count >= 1 && count < Object.keys(DEFAULT_CONFIG).length;
		});
		expect(partials.length).toBeGreaterThan(0);

		process.stdout.write(
			`[VERIFY] P4: corpus_sha256=${digest} cases=${CORPUS.cases.length} categories=${[...categories].sort().join(",")}\n`,
		);
	});
});

describe("autopilot config new-key mirror (P5)", () => {
	it("matches the Python registries byte-for-byte: order, defaults, types, ranges", () => {
		const py = pythonRegistryDump();

		// Key set + order + default values + JSON types.
		expect(Object.keys(DEFAULT_CONFIG)).toEqual(py.keys);
		expect(JSON.stringify(DEFAULT_CONFIG)).toBe(JSON.stringify(py.defaults));

		// The four type registries, order-exact.
		expect([...BOOL_FIELDS]).toEqual(py.bool_fields);
		expect([...LIST_FIELDS]).toEqual(py.list_fields);
		expect([...STR_FIELDS]).toEqual(py.string_fields);
		expect(JSON.stringify(INT_RANGES)).toBe(JSON.stringify(py.int_ranges));

		// The registries partition the 13 keys exactly (no field unclassified,
		// none classified twice).
		const registered = [...py.bool_fields, ...py.list_fields, ...py.string_fields, ...Object.keys(py.int_ranges)];
		expect(registered.length).toBe(py.keys.length);
		expect([...registered].sort()).toEqual([...py.keys].sort());

		// Guards against the null-widening shortcut: the TS ranges must be
		// tuples of numbers / null, never stringified bounds.
		for (const [field, range] of Object.entries(INT_RANGES)) {
			expect(Array.isArray(range), `${field}: range must be a tuple`).toBe(true);
			expect(range.length, `${field}: range arity`).toBe(2);
			expect(typeof range[0], `${field}: lower bound`).toBe("number");
		}

		process.stdout.write(
			`[VERIFY] P5: key_order_match=true defaults_match=true ` +
				`bool=${py.bool_fields.length} list=${py.list_fields.length} ` +
				`str=${py.string_fields.length} int=${Object.keys(py.int_ranges).length}\n`,
		);
	});
});
