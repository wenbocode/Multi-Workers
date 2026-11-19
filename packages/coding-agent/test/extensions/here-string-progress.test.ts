import { runInNewContext } from "node:vm";
import { describe, expect, it } from "vitest";
import {
	classifyLedgerTargets,
	extractBashWriteCandidates,
	stripDataRegions,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

// Bound synchronous regressions: a stuck scanner must fail the test without
// exhausting the test runner's heap. These call the real exported functions.
function strip(command: string): string {
	return runInNewContext("strip(command)", { strip: stripDataRegions, command }, { timeout: 250 }) as string;
}

describe("PowerShell here-string scan progress", () => {
	it.each(["\n", "\r\n"])("strips successive same-quote bodies with %j line endings", (newline) => {
		const command = [
			'python -c @"',
			"first > fake-one",
			'"@; python -c @"',
			"second > fake-two",
			'"@; echo done',
		].join(newline);
		expect(strip(command)).toBe("python -c  ; python -c  ; echo done");
		expect(extractBashWriteCandidates(command)).toEqual([]);
	});

	it("keeps real redirects between and after mixed-quote bodies", () => {
		const command = [
			"$a = @'",
			"body > fake-one",
			"'@",
			"echo first > between.md",
			'$b = @"',
			"body > fake-two",
			'"@',
			"$c = @'",
			"body > fake-three",
			"'@",
			"echo last > after.md",
		].join("\n");
		expect(strip(command)).not.toContain("fake-");
		expect(classifyLedgerTargets(command)).toEqual({ recorded: ["between.md", "after.md"], unresolved: [] });
	});

	it("ignores an earlier closing marker when a later same-quote body is unterminated", () => {
		const command = ['python -c @"', "first", '"@; python -c @"', "unterminated > fake"].join("\n");
		expect(strip(command)).toBe("python -c  ; python -c  ");
	});

	it("keeps inline closing-marker text inside each body inert", () => {
		const command = ['@"', 'inline "@ > fake-one', '"@; @"', 'inline "@ > fake-two', '  "@; echo done'].join("\n");
		expect(strip(command)).toBe(" ;  ; echo done");
	});

	it("handles hundreds of successive here-strings without revisiting previous bodies", () => {
		const command = Array.from({ length: 500 }, (_, index) => `@"\nbody ${index} > fake\n"@;`).join("\n");
		expect(strip(command)).toBe(Array.from({ length: 500 }, () => " ;").join("\n"));
	});
});
