/**
 * worktree-junction-guard-decide.test.ts — W-05 (mw-worktree-junction-guard,
 * G1 AC-001/002/003).
 *
 * Pure-function matrix for `decideWorktreeRemove`. The 2026-10-09 accident
 * command was
 * `cd H:/git/Multi-Workers; git worktree remove --force "$env:TEMP\qg-head"`
 * — a NON-literal target whose worktree held a `node_modules` junction; git
 * walked through the link and deleted 3,456 tracked files from the real
 * tree. This suite pins the resolution pipeline (literal / interpolation /
 * glob+trailing separator / bare-name registry / target-absent) and the
 * reparse-point block text (design §4.3 template + copyable
 * `mw worktree rm "<worktree>"`).
 *
 * W-05b (decision D-11) adds the second covered face: the penetrating forms
 * (`<dir>/`, `<dir>/*`, `<dir>\*`) of `rm` (incl. `-r`/`-rf`/`-f`) and
 * PowerShell `Remove-Item` (incl. `-Recurse`/`-Force`). A registered-worktree
 * target keeps the §4.3 text; any other target gets the second text with the
 * per-link `cmd /c rmdir "<link>"` prescription (AC-002 extension).
 * Separator-free, glob-free operands stay allowed (D-4 rule 3).
 *
 * Fixtures live entirely under `%TEMP%`; every junction target is INSIDE the
 * fixture (never the real tree). Junctions are created with
 * `cmd /c mklink /J` and removed with `cmd /c rmdir` (no `/S`, no trailing
 * separator) before the recursive `rmdir /S /Q` of the fixture root.
 */

import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { decideWorktreeRemove } from "../../src/extensions/agent-team-loop/shared/worktree-junction-guard.ts";

const ROOT = path.join(os.tmpdir(), "wjg-w05-decision");
const CLEAN_WT = path.join(ROOT, "clean-wt");
const PLAIN_DIR = path.join(ROOT, "plain-dir");
const DEPS_REAL = path.join(ROOT, "deps-real");
const DEPS_GONE = path.join(ROOT, "deps-gone");
const JUNCTION_WT = path.join(ROOT, "junction-wt");
const JUNCTION_LINK = path.join(JUNCTION_WT, "node_modules");
const BROKEN_WT = path.join(ROOT, "broken-wt");
const BROKEN_LINK = path.join(BROKEN_WT, "node_modules");
const REPO = path.join(ROOT, "repo");
const AMBIG_A = path.join(ROOT, "p1", "same");
const AMBIG_B = path.join(ROOT, "p2", "same");
const UNIQUE_WT = path.join(ROOT, "uniq-wt");
const UNIQUE_LINK = path.join(UNIQUE_WT, "node_modules");
const LINKS = [JUNCTION_LINK, BROKEN_LINK, UNIQUE_LINK];

const BASE_ENV: NodeJS.ProcessEnv = {
	...process.env,
	TEMP: ROOT,
	WJG_CLEAN: CLEAN_WT,
	WJG_JUNCTION: JUNCTION_WT,
};

interface RunResult {
	status: number | null;
	stdout: string;
	stderr: string;
}

function run(cmd: string, args: string[], cwd?: string): RunResult {
	const result = spawnSync(cmd, args, { cwd, encoding: "utf8", windowsHide: true });
	return { status: result.status, stdout: result.stdout ?? "", stderr: result.stderr ?? "" };
}

function gitOk(args: string[], cwd?: string): RunResult {
	const result = run("git", args, cwd);
	if (result.status !== 0) {
		throw new Error(`git ${args.join(" ")} failed (${result.status}): ${result.stderr}`);
	}
	return result;
}

function mklink(link: string, target: string): void {
	const result = run("cmd", ["/c", "mklink", "/J", link, target]);
	if (result.status !== 0) {
		throw new Error(`mklink /J ${link} ${target} failed (${result.status}): ${result.stderr}`);
	}
}

/** Canonicalize a path for comparison without following the final component
 * (git's `worktree list` emits long 8.3-expanded paths while `os.tmpdir()`
 * can be the short form; a junction must stay the link itself). */
function canonicalPath(value: string): string {
	const dir = path.dirname(value);
	let realDir: string;
	try {
		realDir = fs.realpathSync.native(dir);
	} catch {
		realDir = path.resolve(dir);
	}
	return path.join(realDir, path.basename(value)).toLowerCase();
}

/** The four interpolation spellings of one variable: `$env:N`, `${N}`, `%N%`, `$N`. */
function envVarTokens(name: string): string[] {
	return [`"$env:${name}"`, `"\${${name}}"`, `"%${name}%"`, `"$${name}"`];
}

beforeAll(() => {
	// Previous-run leftovers: drop known links first (never /S, never a
	// trailing separator) so the recursive delete below cannot recurse.
	for (const link of LINKS) run("cmd", ["/c", "rmdir", link]);
	fs.rmSync(ROOT, { recursive: true, force: true });

	fs.mkdirSync(path.join(DEPS_REAL, "sub"), { recursive: true });
	fs.writeFileSync(path.join(DEPS_REAL, "sub", "f.txt"), "fixture\n");
	fs.mkdirSync(DEPS_GONE, { recursive: true });
	fs.mkdirSync(CLEAN_WT, { recursive: true });
	fs.mkdirSync(path.join(PLAIN_DIR, "sub"), { recursive: true });
	fs.writeFileSync(path.join(PLAIN_DIR, "sub", "f.txt"), "plain\n");
	fs.writeFileSync(path.join(PLAIN_DIR, "top.txt"), "plain\n");
	fs.mkdirSync(JUNCTION_WT, { recursive: true });
	mklink(JUNCTION_LINK, DEPS_REAL);

	fs.mkdirSync(BROKEN_WT, { recursive: true });
	mklink(BROKEN_LINK, DEPS_GONE);
	run("cmd", ["/c", "rmdir", DEPS_GONE]); // break the link target

	fs.mkdirSync(REPO, { recursive: true });
	gitOk(["init", "-q"], REPO);
	fs.writeFileSync(path.join(REPO, "a.txt"), "a\n");
	gitOk(["add", "."], REPO);
	gitOk(["-c", "user.email=wjg@test", "-c", "user.name=wjg", "commit", "-qm", "init"], REPO);
	gitOk(["worktree", "add", "--detach", AMBIG_A, "HEAD"], REPO);
	gitOk(["worktree", "add", "--detach", AMBIG_B, "HEAD"], REPO);
	gitOk(["worktree", "add", "--detach", UNIQUE_WT, "HEAD"], REPO);
	mklink(UNIQUE_LINK, DEPS_REAL);
});

afterAll(() => {
	// Hard constraint: unlink each junction with `cmd /c rmdir` (no /S, no
	// trailing separator), then recursive-delete the fixture root only.
	for (const link of LINKS) run("cmd", ["/c", "rmdir", link]);
	run("cmd", ["/c", "rmdir", "/S", "/Q", ROOT]);
	if (fs.existsSync(ROOT)) fs.rmSync(ROOT, { recursive: true, force: true });
});

describe("decideWorktreeRemove — accident shape and interpolation (AC-001/002/003)", () => {
	it("blocks the accident shape: interpolated target whose worktree holds a junction", () => {
		const verdict = decideWorktreeRemove(
			`cd "${REPO}"; git worktree remove --force "$env:TEMP\\junction-wt"`,
			os.tmpdir(),
			BASE_ENV,
		);

		expect(verdict.block).toBe(true);
		expect(verdict.basis).toBe("reparse-point");
		expect(canonicalPath(verdict.target ?? "")).toBe(canonicalPath(JUNCTION_WT));
		expect(verdict.hits.map(canonicalPath)).toEqual([canonicalPath(JUNCTION_LINK)]);
		// AC-002: link path + link target + copyable `mw worktree rm`.
		expect(verdict.reason).toContain("1 个 reparse point");
		expect(verdict.reason).toContain(JUNCTION_LINK);
		expect(verdict.reason).toContain("->");
		expect(verdict.reason).toContain("deps-real");
		expect(verdict.reason).toContain(`  mw worktree rm "${JUNCTION_WT}"`);
	});

	it("blocks a literal path whose worktree holds a junction", () => {
		const verdict = decideWorktreeRemove(`git worktree remove --force "${JUNCTION_WT}"`, os.tmpdir(), BASE_ENV);

		expect(verdict.block).toBe(true);
		expect(verdict.basis).toBe("reparse-point");
		expect(verdict.hits.map(canonicalPath)).toEqual([canonicalPath(JUNCTION_LINK)]);
	});

	it("blocks a broken junction (lstat sees the reparse point, stat cannot)", () => {
		const verdict = decideWorktreeRemove(`git worktree remove --force "${BROKEN_WT}"`, os.tmpdir(), BASE_ENV);

		expect(verdict.block).toBe(true);
		expect(verdict.basis).toBe("reparse-point");
		expect(verdict.hits.map(canonicalPath)).toEqual([canonicalPath(BROKEN_LINK)]);
	});

	it("allows a clean literal worktree (reverse control)", () => {
		const verdict = decideWorktreeRemove(`git worktree remove --force "${CLEAN_WT}"`, os.tmpdir(), BASE_ENV);

		expect(verdict.block).toBe(false);
		expect(verdict.basis).toBe("resolved");
		expect(canonicalPath(verdict.target ?? "")).toBe(canonicalPath(CLEAN_WT));
		expect(verdict.hits).toEqual([]);
	});

	it("allows a resolvable interpolation pointing at a clean worktree (reverse control)", () => {
		for (const token of envVarTokens("WJG_CLEAN")) {
			const verdict = decideWorktreeRemove(`git worktree remove --force ${token}`, os.tmpdir(), BASE_ENV);
			expect(verdict.block, token).toBe(false);
			expect(verdict.basis, token).toBe("resolved");
			expect(canonicalPath(verdict.target ?? ""), token).toBe(canonicalPath(CLEAN_WT));
		}
	});

	it("resolves command-internal assignments before the remove (`$t = ...; remove $t`)", () => {
		const command = `$t = "$env:WJG_JUNCTION"; git worktree remove --force $t`;
		const verdict = decideWorktreeRemove(command, os.tmpdir(), BASE_ENV);

		expect(verdict.block).toBe(true);
		expect(verdict.basis).toBe("reparse-point");
		expect(verdict.hits.map(canonicalPath)).toEqual([canonicalPath(JUNCTION_LINK)]);
	});

	it("blocks an unresolvable variable (fail-closed)", () => {
		const verdict = decideWorktreeRemove('git worktree remove --force "$env:WJG_NOPE_XYZ"', os.tmpdir(), BASE_ENV);

		expect(verdict.block).toBe(true);
		expect(verdict.basis).toBe("unresolved:WJG_NOPE_XYZ");
	});

	it("blocks glob, command substitution and trailing separators", () => {
		const glob = decideWorktreeRemove(`git worktree remove --force "${CLEAN_WT}/*"`, os.tmpdir(), BASE_ENV);
		expect(glob.block).toBe(true);
		expect(glob.basis).toBe("glob");

		const trailing = decideWorktreeRemove(`git worktree remove --force "${CLEAN_WT}/"`, os.tmpdir(), BASE_ENV);
		expect(trailing.block).toBe(true);
		expect(trailing.basis).toBe("glob");

		const substitution = decideWorktreeRemove('git worktree remove --force "$(mktemp -d)/wt"', os.tmpdir(), BASE_ENV);
		expect(substitution.block).toBe(true);
		expect(substitution.basis).toBe("glob");
	});
});

describe("decideWorktreeRemove — bases and non-worktree commands (AC-003)", () => {
	it("resolves a relative operand against the cwd", () => {
		const verdict = decideWorktreeRemove('git worktree remove --force "./junction-wt"', ROOT, BASE_ENV);

		expect(verdict.block).toBe(true);
		expect(verdict.basis).toBe("reparse-point");
		expect(canonicalPath(verdict.target ?? "")).toBe(canonicalPath(JUNCTION_WT));
	});

	it("tracks a preceding `cd` as the base", () => {
		const verdict = decideWorktreeRemove(
			`cd "${ROOT}"; git worktree remove --force "./junction-wt"`,
			os.tmpdir(),
			BASE_ENV,
		);

		expect(verdict.block).toBe(true);
		expect(verdict.basis).toBe("reparse-point");
		expect(canonicalPath(verdict.target ?? "")).toBe(canonicalPath(JUNCTION_WT));
	});

	it("tracks `Set-Location` and lets the `-C` operand override the cwd", () => {
		const viaSetLocation = decideWorktreeRemove(
			`Set-Location "${ROOT}"; git worktree remove --force "./junction-wt"`,
			os.tmpdir(),
			BASE_ENV,
		);
		expect(viaSetLocation.block).toBe(true);
		expect(canonicalPath(viaSetLocation.target ?? "")).toBe(canonicalPath(JUNCTION_WT));

		// `cd` points elsewhere; the `-C` operand is the base for the relative operand.
		const viaDashC = decideWorktreeRemove(
			`cd "${os.tmpdir()}"; git -C "${ROOT}" worktree remove --force "./junction-wt"`,
			os.tmpdir(),
			BASE_ENV,
		);
		expect(viaDashC.block).toBe(true);
		expect(viaDashC.basis).toBe("reparse-point");
		expect(canonicalPath(viaDashC.target ?? "")).toBe(canonicalPath(JUNCTION_WT));
	});

	it("blocks a bare name with a unique registry match pointing at a junction", () => {
		const verdict = decideWorktreeRemove(`git -C "${REPO}" worktree remove --force uniq-wt`, os.tmpdir(), BASE_ENV);

		expect(verdict.block).toBe(true);
		expect(verdict.basis).toBe("reparse-point");
		expect(canonicalPath(verdict.target ?? "")).toBe(canonicalPath(UNIQUE_WT));
		expect(verdict.hits.map(canonicalPath)).toEqual([canonicalPath(UNIQUE_LINK)]);
	});

	it("blocks an ambiguous bare name (two worktrees share the basename)", () => {
		const verdict = decideWorktreeRemove(`git -C "${REPO}" worktree remove --force same`, os.tmpdir(), BASE_ENV);

		expect(verdict.block).toBe(true);
		expect(verdict.basis).toBe("bare-name-ambiguous");
	});

	it("allows a bare name with no registry match (git rejects with rc=128)", () => {
		const verdict = decideWorktreeRemove(
			`git -C "${REPO}" worktree remove --force no-such-worktree-xyz`,
			os.tmpdir(),
			BASE_ENV,
		);

		expect(verdict.block).toBe(false);
		expect(verdict.basis).toBe("target-absent");
	});

	it("allows a target that does not exist (git is a no-op, rc=128)", () => {
		const verdict = decideWorktreeRemove(
			`git worktree remove --force "${path.join(ROOT, "does-not-exist")}"`,
			os.tmpdir(),
			BASE_ENV,
		);

		expect(verdict.block).toBe(false);
		expect(verdict.basis).toBe("target-absent");
	});

	it("allows only the out-of-scope forms for non-git verbs (D-4 rule 3, D-11 boundary)", () => {
		for (const command of [
			`rm -rf "${JUNCTION_WT}"`,
			`rmdir /S /Q "${JUNCTION_WT}"`,
			`Remove-Item -Recurse -Force "${JUNCTION_WT}"`,
			`robocopy "${JUNCTION_WT}" "${CLEAN_WT}" /MIR`,
			`git worktree list`,
			`git worktree add "${path.join(ROOT, "new-wt")}"`,
			`git status --short`,
		]) {
			const verdict = decideWorktreeRemove(command, os.tmpdir(), BASE_ENV);
			expect(verdict.block, command).toBe(false);
			expect(verdict.basis, command).toBe("not-remove");
		}
	});
});

describe("decideWorktreeRemove — rm/Remove-Item penetrating forms (D-11, AC-002 extension)", () => {
	it("blocks `rm -rf <dir-with-junction>/` with the rmdir prescription (non-worktree target)", () => {
		const verdict = decideWorktreeRemove(`rm -rf "${JUNCTION_WT}/"`, os.tmpdir(), BASE_ENV);

		expect(verdict.block).toBe(true);
		expect(verdict.basis).toBe("delete-penetration");
		expect(canonicalPath(verdict.target ?? "")).toBe(canonicalPath(JUNCTION_WT));
		expect(verdict.hits.map(canonicalPath)).toEqual([canonicalPath(JUNCTION_LINK)]);
		// AC-002 extension: penetrating form + link chain + copyable rmdir (no /S).
		expect(verdict.reason).toContain("穿透 reparse point");
		expect(verdict.reason).toContain(JUNCTION_LINK);
		expect(verdict.reason).toContain("->");
		expect(verdict.reason).toContain("deps-real");
		expect(verdict.reason).toContain(`  cmd /c rmdir "${JUNCTION_LINK}"`);
		expect(verdict.reason).not.toContain("mw worktree rm");
	});

	it('blocks `rm -rf "<dir>/*"` (POSIX glob form)', () => {
		const verdict = decideWorktreeRemove(`rm -rf "${JUNCTION_WT}/*"`, os.tmpdir(), BASE_ENV);

		expect(verdict.block).toBe(true);
		expect(verdict.basis).toBe("delete-penetration");
		expect(canonicalPath(verdict.target ?? "")).toBe(canonicalPath(JUNCTION_WT));
		expect(verdict.hits.map(canonicalPath)).toEqual([canonicalPath(JUNCTION_LINK)]);
		expect(verdict.reason).toContain(`  cmd /c rmdir "${JUNCTION_LINK}"`);
	});

	it('blocks `Remove-Item -Recurse -Force "<dir>\\*"` (PowerShell glob form)', () => {
		const verdict = decideWorktreeRemove(`Remove-Item -Recurse -Force "${JUNCTION_WT}\\*"`, os.tmpdir(), BASE_ENV);

		expect(verdict.block).toBe(true);
		expect(verdict.basis).toBe("delete-penetration");
		expect(canonicalPath(verdict.target ?? "")).toBe(canonicalPath(JUNCTION_WT));
		expect(verdict.reason).toContain(`  cmd /c rmdir "${JUNCTION_LINK}"`);
	});

	it('blocks `Remove-Item -Recurse -Force "<dir>/"` (PowerShell trailing-separator form)', () => {
		const verdict = decideWorktreeRemove(`Remove-Item -Recurse -Force "${JUNCTION_WT}/"`, os.tmpdir(), BASE_ENV);

		expect(verdict.block).toBe(true);
		expect(verdict.basis).toBe("delete-penetration");
		expect(canonicalPath(verdict.target ?? "")).toBe(canonicalPath(JUNCTION_WT));
	});

	it("blocks `rm -rf <worktree-with-junction>/` with the §4.3 `mw worktree rm` text", () => {
		const verdict = decideWorktreeRemove(`rm -rf "${UNIQUE_WT}/"`, os.tmpdir(), BASE_ENV);

		expect(verdict.block).toBe(true);
		expect(verdict.basis).toBe("reparse-point");
		expect(canonicalPath(verdict.target ?? "")).toBe(canonicalPath(UNIQUE_WT));
		expect(verdict.hits.map(canonicalPath)).toEqual([canonicalPath(UNIQUE_LINK)]);
		expect(verdict.reason).toContain(`  mw worktree rm "${UNIQUE_WT}"`);
	});

	it("blocks an interpolated penetrating operand, and fails closed on an unknown variable", () => {
		const viaEnv = decideWorktreeRemove('rm -rf "$env:WJG_JUNCTION/"', os.tmpdir(), BASE_ENV);
		expect(viaEnv.block).toBe(true);
		expect(viaEnv.basis).toBe("delete-penetration");
		expect(canonicalPath(viaEnv.target ?? "")).toBe(canonicalPath(JUNCTION_WT));

		const unknown = decideWorktreeRemove('rm -rf "$env:WJG_NOPE_XYZ/"', os.tmpdir(), BASE_ENV);
		expect(unknown.block).toBe(true);
		expect(unknown.basis).toBe("unresolved:WJG_NOPE_XYZ");
	});
});

describe("decideWorktreeRemove — delete-form reverse controls (D-4 rule 3, no false positives)", () => {
	it("allows separator-free / clean / plain targets and non-covered verbs", () => {
		const allowed: Array<[string, string]> = [
			[`rm -rf "${JUNCTION_WT}"`, "not-remove"],
			[`rm -rf "${CLEAN_WT}/"`, "resolved"],
			[`rm -rf "${PLAIN_DIR}/"`, "resolved"],
			[`ls "${JUNCTION_WT}/"`, "not-remove"],
			[`rmdir /S /Q "${JUNCTION_WT}"`, "not-remove"],
		];
		for (const [command, basis] of allowed) {
			const verdict = decideWorktreeRemove(command, os.tmpdir(), BASE_ENV);
			expect(verdict.block, command).toBe(false);
			expect(verdict.basis, command).toBe(basis);
		}
	});
});

describe("decideWorktreeRemove — prescription allow face (F-06, AC-003 reverse control)", () => {
	it("allows both G1 prescriptions verbatim and the cd-prefixed spelling", () => {
		// Machine fact, not assumption: the fixture junction exists on disk and
		// the guard really sees it, so the allow assertions below are not vacuous.
		expect(fs.lstatSync(JUNCTION_LINK).isSymbolicLink()).toBe(true);
		expect(canonicalPath(fs.realpathSync.native(JUNCTION_LINK))).toBe(canonicalPath(DEPS_REAL));
		const hazard = decideWorktreeRemove(`git worktree remove --force "${JUNCTION_WT}"`, os.tmpdir(), BASE_ENV);
		expect(hazard.block).toBe(true);
		expect(hazard.basis).toBe("reparse-point");

		const prescriptions: Array<[string, string]> = [
			// §4.3 text: registered-worktree prescription.
			[`mw worktree rm "${JUNCTION_WT}"`, "处方一 mw worktree rm"],
			// D-11 second text: per-link unlink prescription (no /S).
			[`cmd /c rmdir "${JUNCTION_LINK}"`, "处方二 cmd /c rmdir"],
			// Both prescriptions commonly follow a leading `cd`.
			[`cd "${ROOT}"; mw worktree rm "${JUNCTION_WT}"`, "处方一 + 前导 cd"],
		];
		for (const [command, label] of prescriptions) {
			const verdict = decideWorktreeRemove(command, os.tmpdir(), BASE_ENV);
			expect(verdict.block, label).toBe(false);
			expect(verdict.basis, label).toBe("not-remove");
			expect(verdict.hits, label).toEqual([]);
		}
	});

	it("keeps the trailing-separator mis-spelling of the rmdir prescription out of the block face", () => {
		// The prescription is copied verbatim WITHOUT a trailing separator; a
		// trailing separator is a mis-spelling. This pins the ACTUAL behavior
		// verbatim with its `cmd` head word, it does not ask for a change.
		expect(fs.lstatSync(JUNCTION_LINK).isSymbolicLink()).toBe(true);
		const misSpellings: Array<[string, string]> = [
			[`cmd /c rmdir "${JUNCTION_LINK}/"`, "尾斜杠"],
			[`cmd /c rmdir "${JUNCTION_LINK}\\"`, "尾反斜杠"],
		];
		for (const [command, label] of misSpellings) {
			const verdict = decideWorktreeRemove(command, os.tmpdir(), BASE_ENV);
			expect(verdict.block, label).toBe(false);
			expect(verdict.basis, label).toBe("not-remove");
		}
	});
});

/**
 * W-17 (D-19). Pi's shell is pinned to PowerShell (`mw_common.ensure_pi_shell_path`),
 * so `<link>/`/`<link>/*` deletions spelled with `ri`/`del`/`erase`/`rd`/`rmdir`
 * have exactly the same reach as `Remove-Item -Recurse`, and `cd /d`/`pushd`/`sl`
 * drift the base the same way `cd` does. D-19 only extends the verb/flag
 * vocabulary; the recursive-flag, trailing-separator/glob and `notRemove`
 * predicates and the prescription texts are unchanged.
 */
describe("decideWorktreeRemove — PowerShell/cmd verb vocabulary (D-19)", () => {
	it("tracks `pushd` / `sl` / `chdir` as the base for a following relative remove (baseline drift)", () => {
		for (const verb of ["pushd", "sl", "chdir"]) {
			const verdict = decideWorktreeRemove(
				`${verb} "${ROOT}"; git worktree remove --force "./uniq-wt"`,
				os.tmpdir(),
				BASE_ENV,
			);
			expect(verdict.block, verb).toBe(true);
			expect(verdict.basis, verb).toBe("reparse-point");
			expect(canonicalPath(verdict.target ?? ""), verb).toBe(canonicalPath(UNIQUE_WT));
			expect(verdict.hits.map(canonicalPath), verb).toEqual([canonicalPath(UNIQUE_LINK)]);
		}
	});

	it("skips the cmd-style `/d` / `/D` flag and takes the real operand (`cd /d <dir>`)", () => {
		for (const flag of ["/d", "/D"]) {
			const verdict = decideWorktreeRemove(
				`cd ${flag} "${ROOT}"; git worktree remove --force "./uniq-wt"`,
				os.tmpdir(),
				BASE_ENV,
			);
			expect(verdict.block, flag).toBe(true);
			expect(verdict.basis, flag).toBe("reparse-point");
			expect(canonicalPath(verdict.target ?? ""), flag).toBe(canonicalPath(UNIQUE_WT));
		}
	});

	it("takes the value of `-Path <dir>`, `-Path=<dir>` and `-LiteralPath=<dir>`", () => {
		const prefixes = [
			`Set-Location -Path "${ROOT}"`,
			`Set-Location -Path="${ROOT}"`,
			`Set-Location -LiteralPath="${ROOT}"`,
			`sl -Path "${ROOT}"`,
		];
		for (const prefix of prefixes) {
			const verdict = decideWorktreeRemove(
				`${prefix}; git worktree remove --force "./uniq-wt"`,
				os.tmpdir(),
				BASE_ENV,
			);
			expect(verdict.block, prefix).toBe(true);
			expect(verdict.basis, prefix).toBe("reparse-point");
			expect(canonicalPath(verdict.target ?? ""), prefix).toBe(canonicalPath(UNIQUE_WT));
		}
	});

	it("fails closed on a location verb without a target (bare `pushd` -> home, base unprovable)", () => {
		const verdict = decideWorktreeRemove('pushd; git worktree remove --force "./uniq-wt"', os.tmpdir(), BASE_ENV);
		expect(verdict.block).toBe(true);
		expect(verdict.basis).toBe("unresolved:pushd");
	});

	it("allows the clean baseline verbs alone, with no following delete (reverse control)", () => {
		const commands = [`sl "${ROOT}"`, `chdir "${ROOT}"`, `pushd "${ROOT}"`, `cd /d "${ROOT}"`, "pushd"];
		for (const command of commands) {
			const verdict = decideWorktreeRemove(command, os.tmpdir(), BASE_ENV);
			expect(verdict.block, command).toBe(false);
			expect(verdict.basis, command).toBe("not-remove");
		}
	});

	it("blocks every new delete verb in a penetrating form with the second text", () => {
		const cases: Array<[string, string]> = [
			[`ri -r -fo "${JUNCTION_WT}/"`, "ri"],
			[`del -Recurse "${JUNCTION_WT}/*"`, "del"],
			[`erase -Recurse "${JUNCTION_WT}/"`, "erase"],
			[`rd -Recurse "${JUNCTION_WT}/*"`, "rd"],
			[`rmdir -Recurse "${JUNCTION_WT}/"`, "rmdir"],
		];
		for (const [command, label] of cases) {
			const verdict = decideWorktreeRemove(command, os.tmpdir(), BASE_ENV);
			expect(verdict.block, label).toBe(true);
			expect(verdict.basis, label).toBe("delete-penetration");
			expect(canonicalPath(verdict.target ?? ""), label).toBe(canonicalPath(JUNCTION_WT));
			expect(verdict.hits.map(canonicalPath), label).toEqual([canonicalPath(JUNCTION_LINK)]);
			expect(verdict.reason, label).toContain(`  cmd /c rmdir "${JUNCTION_LINK}"`);
			expect(verdict.reason, label).not.toContain("mw worktree rm");
		}
	});

	it("allows separator-free / glob-free operands of the new delete verbs (reverse control)", () => {
		const file = path.join(ROOT, "file.txt");
		const allowed: Array<[string, string]> = [
			[`del "${file}"`, "del"],
			[`ri "${file}"`, "ri"],
			[`erase "${file}"`, "erase"],
			[`rd "${PLAIN_DIR}"`, "rd"],
			[`rmdir /S "${JUNCTION_WT}"`, "rmdir /S"],
		];
		for (const [command, label] of allowed) {
			const verdict = decideWorktreeRemove(command, os.tmpdir(), BASE_ENV);
			expect(verdict.block, label).toBe(false);
			expect(verdict.basis, label).toBe("not-remove");
		}
	});

	it("keeps the existing prescriptions allowed by head word, not by substring (reverse control)", () => {
		const prescriptions = [
			`mw worktree rm "${JUNCTION_WT}"`,
			`cmd /c rmdir "${JUNCTION_LINK}"`,
			`cmd /c rmdir "${JUNCTION_LINK}/"`,
		];
		for (const command of prescriptions) {
			const verdict = decideWorktreeRemove(command, os.tmpdir(), BASE_ENV);
			expect(verdict.block, command).toBe(false);
			expect(verdict.basis, command).toBe("not-remove");
		}
	});
});
