/**
 * bash-segments.test.ts — W-01 (mw-worktree-junction-guard, D-3).
 *
 * The G1 pre-execution interception layer resolves targets from a command
 * string, so the target of the accident command
 * `git worktree remove --force "$env:TEMP\qg-head"` must first survive
 * lexing unchanged: quotes stripped, interpolation NOT expanded. This suite
 * pins that contract on the extracted shared lexer
 * (shared/bash-segments.ts) — the single copy both consumers use, so the
 * judgement side and the guard side cannot drift (IN-3 class).
 *
 * Pure unit tests: inline command literals only, no filesystem, no provider.
 */

import { describe, expect, it } from "vitest";
import { parseBashSegments } from "../../src/extensions/agent-team-loop/shared/bash-segments.ts";

/** All argv words across every segment (order preserved). */
function words(command: string): string[] {
	return parseBashSegments(command).flatMap((segment) => segment.words);
}

describe("shared bash segment lexer (W-01 / D-3)", () => {
	it("keeps the accident command's quoted non-literal target intact (quotes stripped, no expansion)", () => {
		const command = 'git worktree remove --force "$env:TEMP\\qg-head"';
		const segments = parseBashSegments(command);

		expect(segments).toHaveLength(1);
		expect(segments[0]?.words).toEqual(["git", "worktree", "remove", "--force", "$env:TEMP\\qg-head"]);
		expect(segments[0]?.redirectTargets).toEqual([]);
		// The resolution layer reads these raw tokens: the verb words and the
		// interpolated path token are present verbatim, `$env:TEMP` is not
		// expanded and the Windows separator backslash is not eaten.
		const flat = words(command);
		for (const token of ["worktree", "remove", "--force"]) {
			expect(flat).toContain(token);
		}
		expect(flat).toContain("$env:TEMP\\qg-head");
	});

	it("separates a `cd` base segment from the following command segment at `;`", () => {
		const segments = parseBashSegments(
			"cd H:/git/Multi-Workers; git worktree remove --force H:/git/Multi-Workers/packages/x",
		);

		expect(segments).toHaveLength(2);
		expect(segments[0]?.words).toEqual(["cd", "H:/git/Multi-Workers"]);
		expect(segments[1]?.words).toEqual(["git", "worktree", "remove", "--force", "H:/git/Multi-Workers/packages/x"]);
	});

	it("strips quotes without expanding `$`; single vs double quotes differ only in backslash escaping", () => {
		// Bare and quoted `$` are all literal text for the lexer (it never expands).
		expect(words("echo $HOME")).toEqual(["echo", "$HOME"]);
		expect(words("echo '$HOME'")).toEqual(["echo", "$HOME"]);
		expect(words('echo "$HOME"')).toEqual(["echo", "$HOME"]);
		// Inside double quotes `\$` is an escape (POSIX), so the backslash is
		// consumed; inside single quotes the backslash is literal payload.
		expect(words('echo "\\$HOME"')).toEqual(["echo", "$HOME"]);
		expect(words("echo '\\$HOME'")).toEqual(["echo", "\\$HOME"]);
	});

	it("splits segments at `;`, `|`, `&&` and `||`", () => {
		expect(parseBashSegments("a ; b").map((segment) => segment.words)).toEqual([["a"], ["b"]]);
		expect(parseBashSegments("cat a | tee b").map((segment) => segment.words)).toEqual([
			["cat", "a"],
			["tee", "b"],
		]);
		expect(parseBashSegments("a && b").map((segment) => segment.words)).toEqual([["a"], ["b"]]);
		expect(parseBashSegments("a || b").map((segment) => segment.words)).toEqual([["a"], ["b"]]);
	});

	it("skips heredoc bodies as payload and still lexes the command that follows", () => {
		const command = [
			"cat <<EOF",
			"git worktree remove --force /tmp/inside-body",
			"echo redirect > /tmp/inside-body-redirect",
			"EOF",
			"echo after-heredoc",
		].join("\n");
		const segments = parseBashSegments(command);
		const flat = segments.flatMap((segment) => segment.words);

		// The command after the heredoc terminator is lexed...
		expect(flat).toContain("cat");
		expect(flat).toContain("echo");
		expect(flat).toContain("after-heredoc");
		// ...while the body's shell-looking text (including its redirect) is not.
		expect(flat).not.toContain("worktree");
		expect(flat).not.toContain("remove");
		expect(flat).not.toContain("--force");
		expect(flat).not.toContain("/tmp/inside-body");
		expect(flat).not.toContain("/tmp/inside-body-redirect");
		expect(segments.flatMap((segment) => segment.redirectTargets)).toEqual([]);
	});

	it("captures redirect targets separately from argv words", () => {
		const segments = parseBashSegments("echo x > /tmp/out 2> /tmp/err");

		expect(segments).toHaveLength(1);
		expect(segments[0]?.words).toEqual(["echo", "x"]);
		expect(segments[0]?.redirectTargets).toEqual(["/tmp/out", "/tmp/err"]);
	});
});
