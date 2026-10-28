/**
 * Review-split switch tests (claim-driven-review-orchestration T-01,
 * design §2.2, spec AC-S1).
 *
 * The resolver is pure decision logic over (env, one JSON file): fixtures are
 * temp project roots under os.tmpdir() so the repo's real `.mw` is never
 * touched. Every case also pins the two properties the callers depend on —
 * the returned source (`env`/`config`/`default`, echoed by
 * `mw review-split status`) and the never-throws/pure-read contract.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
	REVIEW_SPLIT_CONFIG,
	REVIEW_SPLIT_DEFAULT,
	REVIEW_SPLIT_ENV,
	REVIEW_SPLIT_MODES,
	type ReviewSplitMode,
	type ReviewSplitSource,
	resolveReviewSplit,
	reviewSplitConfigPath,
} from "../../src/extensions/agent-team-loop/shared/review-split.ts";

let projectDir: string;
let configPath: string;

function writeConfig(value: unknown): void {
	fs.mkdirSync(path.join(projectDir, ".mw"), { recursive: true });
	fs.writeFileSync(configPath, JSON.stringify(value), "utf-8");
}

beforeEach(() => {
	projectDir = fs.mkdtempSync(path.join(os.tmpdir(), "mw-review-split-"));
	configPath = reviewSplitConfigPath(projectDir);
});

afterEach(() => {
	fs.rmSync(projectDir, { recursive: true, force: true });
});

describe("resolveReviewSplit", () => {
	it("defaults to off/default when neither env nor config exists (pure read)", () => {
		const state = resolveReviewSplit(projectDir, {});

		expect(state).toEqual({ mode: "off", source: "default", configPath });
		expect(state.invalid).toBeUndefined();
		expect(REVIEW_SPLIT_DEFAULT).toBe("off");
		expect(REVIEW_SPLIT_MODES).toEqual(["off", "plan", "on"]);
		expect(REVIEW_SPLIT_CONFIG).toBe(".mw/review-split.json");
		// Pure read: resolving must not create `.mw` or the config file.
		expect(fs.readdirSync(projectDir)).toEqual([]);
		expect(fs.existsSync(configPath)).toBe(false);
	});

	it("env on wins and reports source env", () => {
		const state = resolveReviewSplit(projectDir, { [REVIEW_SPLIT_ENV]: "on" });

		expect(state).toEqual({ mode: "on", source: "env", configPath });
		expect(state.invalid).toBeUndefined();
		expect(REVIEW_SPLIT_ENV).toBe("MW_REVIEW_SPLIT");
		expect(configPath).toBe(path.join(projectDir, ".mw", "review-split.json"));
	});

	it("illegal env value is ignored (as if unset), reported in invalid, and falls through", () => {
		const noConfig = resolveReviewSplit(projectDir, { MW_REVIEW_SPLIT: "true" });

		expect(noConfig.mode).toBe("off");
		expect(noConfig.source).toBe("default");
		expect(noConfig.invalid).toBe("true");

		// Empty env value: also "as if unset" (the raw "" rides along, falsy
		// for the caller's warning check).
		const emptyEnv = resolveReviewSplit(projectDir, { MW_REVIEW_SPLIT: "" });
		expect(emptyEnv.mode).toBe("off");
		expect(emptyEnv.source).toBe("default");
		expect(emptyEnv.invalid).toBe("");

		// With a valid config present the illegal env value must not block it.
		writeConfig({ v: 1, mode: "plan" });
		const withConfig = resolveReviewSplit(projectDir, { MW_REVIEW_SPLIT: "true" });
		expect(withConfig.mode).toBe("plan");
		expect(withConfig.source).toBe("config");
		expect(withConfig.invalid).toBe("true");
	});

	it("env mode matching is case-insensitive and whitespace tolerant", () => {
		expect(resolveReviewSplit(projectDir, { MW_REVIEW_SPLIT: "Plan" })).toEqual({
			mode: "plan",
			source: "env",
			configPath,
		});
		expect(resolveReviewSplit(projectDir, { MW_REVIEW_SPLIT: "ON" }).mode).toBe("on");
		expect(resolveReviewSplit(projectDir, { MW_REVIEW_SPLIT: " Off " })).toEqual({
			mode: "off",
			source: "env",
			configPath,
		});
	});

	it('config {"v":1,"mode":"plan"} resolves plan/config', () => {
		writeConfig({ v: 1, mode: "plan", updated: "2026-10-22T00:00:00.000Z" });

		const state = resolveReviewSplit(projectDir, {});
		expect(state).toEqual({ mode: "plan", source: "config", configPath });
		expect(state.invalid).toBeUndefined();

		writeConfig({ v: 1, mode: "off" });
		expect(resolveReviewSplit(projectDir, {})).toEqual({ mode: "off", source: "config", configPath });
	});

	it("env overrides config in both directions", () => {
		writeConfig({ v: 1, mode: "plan" });
		expect(resolveReviewSplit(projectDir, { MW_REVIEW_SPLIT: "off" })).toEqual({
			mode: "off",
			source: "env",
			configPath,
		});

		writeConfig({ v: 1, mode: "off" });
		expect(resolveReviewSplit(projectDir, { MW_REVIEW_SPLIT: "on" })).toEqual({
			mode: "on",
			source: "env",
			configPath,
		});
	});

	it("corrupt / non-object config JSON degrades to default with a reason", () => {
		fs.mkdirSync(path.join(projectDir, ".mw"), { recursive: true });
		fs.writeFileSync(configPath, "{ not json", "utf-8");

		const broken = resolveReviewSplit(projectDir, {});
		expect(broken.mode).toBe("off");
		expect(broken.source).toBe("default");
		expect(broken.invalid).toBe("config-invalid-json");
		// Pure read: the corrupt file is left exactly as it was.
		expect(fs.readFileSync(configPath, "utf-8")).toBe("{ not json");

		fs.writeFileSync(configPath, "[]", "utf-8");
		const nonObject = resolveReviewSplit(projectDir, {});
		expect(nonObject.mode).toBe("off");
		expect(nonObject.source).toBe("default");
		expect(nonObject.invalid).toBe("config-invalid-shape");
	});

	it("config with an illegal mode (or wrong format version) degrades to default", () => {
		writeConfig({ v: 1, mode: "fast" });
		const badMode = resolveReviewSplit(projectDir, {});
		expect(badMode.mode).toBe("off");
		expect(badMode.source).toBe("default");
		expect(badMode.invalid).toContain("config-invalid-mode");
		expect(badMode.invalid).toContain("fast");

		writeConfig({ v: 2, mode: "plan" });
		const badVersion = resolveReviewSplit(projectDir, {});
		expect(badVersion.mode).toBe("off");
		expect(badVersion.source).toBe("default");
		expect(badVersion.invalid).toBe("config-invalid-v:2");

		writeConfig({ mode: "plan" });
		const missingVersion = resolveReviewSplit(projectDir, {});
		expect(missingVersion.source).toBe("default");
		expect(missingVersion.invalid).toContain("config-invalid-v");
	});
});

/**
 * Cross-language parity (T-05): the SAME table is read by the Python parity
 * suite (`packages/multi-workers/test_review_split_parity.py`), so agreement
 * between the two resolvers is pinned by one corpus instead of by hand-copied
 * expectations. `config: null` = no config file, a string = written verbatim
 * (corrupt JSON), anything else = `JSON.stringify`-ed into the switch file.
 */
interface SharedSplitCase {
	name: string;
	env: Record<string, string>;
	config: unknown;
	expect: { mode: ReviewSplitMode; source: ReviewSplitSource; invalid: string | null };
}

const SHARED_CASES = JSON.parse(
	fs.readFileSync(new URL("./fixtures/review-split-cases.json", import.meta.url), "utf8"),
) as SharedSplitCase[];

const REQUIRED_CASE_NAMES = [
	"default-no-env-no-config",
	"env-on",
	"env-uppercase-plan",
	"env-illegal-no-config",
	"config-plan",
	"env-on-overrides-config-plan",
	"config-broken-json",
	"config-v2-unsupported",
	"config-mode-illegal",
];

describe("resolveReviewSplit (shared cross-language table)", () => {
	function writeCaseConfig(config: unknown): void {
		if (config === null) return;
		fs.mkdirSync(path.join(projectDir, ".mw"), { recursive: true });
		fs.writeFileSync(configPath, typeof config === "string" ? config : JSON.stringify(config), "utf-8");
	}

	it("corpus covers the required scenarios", () => {
		expect(SHARED_CASES.length).toBeGreaterThanOrEqual(9);
		const names = SHARED_CASES.map((testCase) => testCase.name);
		expect(new Set(names).size).toBe(names.length);
		for (const required of REQUIRED_CASE_NAMES) {
			expect(names).toContain(required);
		}
	});

	for (const testCase of SHARED_CASES) {
		it(`table: ${testCase.name}`, () => {
			writeCaseConfig(testCase.config);

			const state = resolveReviewSplit(projectDir, testCase.env);

			expect(state.mode).toBe(testCase.expect.mode);
			expect(state.source).toBe(testCase.expect.source);
			// `invalid` is absent in the TS state when nothing was rejected; the
			// table spells that out as null.
			expect(state.invalid ?? null).toBe(testCase.expect.invalid);
			expect(state.configPath).toBe(configPath);
		});
	}
});
