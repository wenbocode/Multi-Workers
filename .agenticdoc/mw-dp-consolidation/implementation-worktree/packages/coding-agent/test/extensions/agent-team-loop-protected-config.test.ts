/**
 * Tests for the cross-window protected-config guard (mw-protected-config-guard).
 *
 * Incident 2026-09-15: a running session cleared ~/.pi/agent/auth.json; every
 * other live pi window lost its credentials ("Provider is not configured")
 * and several hung. The guard hard-blocks write/edit/bash tool calls that
 * would modify the shared agent config while sessions run; reads pass.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { describe, expect, it } from "vitest";
import {
	checkProtectedBashCommand,
	isProtectedConfigPath,
	protectedConfigPaths,
	recordProtectedBlockTrace,
	resolveAgentDir,
} from "../../src/extensions/agent-team-loop/shared/protected-config.ts";

const HOME = os.homedir();
const AGENT_DIR = path.join(HOME, ".pi", "agent");

describe("protected-config: resolveAgentDir", () => {
	it("defaults to ~/.pi/agent and honors the PI_CODING_AGENT_DIR override", () => {
		expect(resolveAgentDir({})).toBe(AGENT_DIR);
		expect(resolveAgentDir({ PI_CODING_AGENT_DIR: path.join(HOME, "agent-alt") })).toBe(path.join(HOME, "agent-alt"));
		// Tilde form is expanded like core getAgentDir()'s normalizePath.
		expect(resolveAgentDir({ PI_CODING_AGENT_DIR: "~/agent-alt" })).toBe(path.join(HOME, "agent-alt"));
	});
});

describe("protected-config: protectedConfigPaths", () => {
	it("covers the four shared agent config files", () => {
		const files = protectedConfigPaths(AGENT_DIR).map((p) => path.basename(p));
		expect(files).toEqual(["auth.json", "models.json", "settings.json", "oauth.json"]);
	});
});

describe("protected-config: isProtectedConfigPath (write/edit tools)", () => {
	it("blocks absolute, tilde, and cwd-relative spellings of the protected files", () => {
		expect(isProtectedConfigPath(AGENT_DIR, path.join(AGENT_DIR, "auth.json"))).toBe(true);
		expect(isProtectedConfigPath(AGENT_DIR, "~/.pi/agent/auth.json")).toBe(true);
		expect(isProtectedConfigPath(AGENT_DIR, "~\\.pi\\agent\\models.json")).toBe(true);
		expect(isProtectedConfigPath(AGENT_DIR, "auth.json", AGENT_DIR)).toBe(true);
		// The agent dir itself (delete/replace semantics) is protected too.
		expect(isProtectedConfigPath(AGENT_DIR, "~/.pi/agent")).toBe(true);
	});

	it("allows everything else, including near-miss names and agentDir siblings", () => {
		expect(isProtectedConfigPath(AGENT_DIR, "src/index.ts", "/repo")).toBe(false);
		expect(isProtectedConfigPath(AGENT_DIR, "auth.json", "/repo")).toBe(false);
		expect(isProtectedConfigPath(AGENT_DIR, path.join(AGENT_DIR, "sessions", "x.json"))).toBe(false);
		expect(isProtectedConfigPath(AGENT_DIR, path.join(AGENT_DIR, "extensions", "agent-team-loop.js"))).toBe(false);
		// Directory boundary: agent-alt / agentx are different trees.
		expect(isProtectedConfigPath(AGENT_DIR, "~/.pi/agent-alt/auth.json")).toBe(false);
		expect(isProtectedConfigPath(AGENT_DIR, "~/.pi/agentx/auth.json")).toBe(false);
	});
});

describe("protected-config: checkProtectedBashCommand", () => {
	it("blocks the incident-shaped writes (rm/del/redirect/PowerShell/sed/find)", () => {
		const blocked = [
			"rm ~/.pi/agent/auth.json",
			"rm -rf ~/.pi/agent",
			"mv ~/.pi/agent/auth.json /tmp/bak",
			"cp /tmp/credentials ~/.pi/agent/models.json",
			"echo {} > ~/.pi/agent/auth.json",
			"cat junk >> ~/.pi/agent/settings.json",
			`del %USERPROFILE%\\.pi\\agent\\auth.json`,
			"Set-Content -Path $env:USERPROFILE\\.pi\\agent\\auth.json -Value 'x'",
			"Remove-Item ~\\.pi\\agent\\oauth.json",
			"sed -i 's/a/b/' ~/.pi/agent/models.json",
			"find ~/.pi/agent -name auth.json -delete",
			"touch ~/.pi/agent/auth.json",
		];
		for (const cmd of blocked) {
			const verdict = checkProtectedBashCommand(AGENT_DIR, cmd);
			expect(verdict.prohibited, cmd).toBe(true);
			expect(verdict.reason, cmd).toContain("cross-window config");
		}
	});

	it("blocks inline code writes, including assembled paths the expansion cannot fold", () => {
		expect(
			checkProtectedBashCommand(AGENT_DIR, `python -c "open(r'~/.pi/agent/auth.json','w').write('x')"`).prohibited,
		).toBe(true);
		expect(
			checkProtectedBashCommand(
				AGENT_DIR,
				`node -e "fs.writeFileSync(process.env.HOME + '/.pi/agent/auth.json', '')"`,
			).prohibited,
		).toBe(true);
	});

	it("matches the custom PI_CODING_AGENT_DIR dir through its env spellings", () => {
		const custom = path.join(HOME, "agent-custom");
		expect(checkProtectedBashCommand(custom, "rm $PI_CODING_AGENT_DIR/auth.json").prohibited).toBe(true);
		expect(checkProtectedBashCommand(custom, `rm \${PI_CODING_AGENT_DIR}/models.json`).prohibited).toBe(true);
	});

	it("allows reads and redirects away from the protected paths", () => {
		const allowed = [
			"cat ~/.pi/agent/auth.json",
			"rg timi ~/.pi/agent/auth.json",
			"ls ~/.pi/agent",
			"cat ~/.pi/agent/auth.json > /tmp/out.txt",
			"echo x > /tmp/out && cat ~/.pi/agent/auth.json",
			`python -c "print(open('$HOME/.pi/agent/auth.json').read())"`,
			"cd ~ && cat .pi/agent/auth.json",
			"python --version",
		];
		for (const cmd of allowed) {
			expect(checkProtectedBashCommand(AGENT_DIR, cmd).prohibited, cmd).toBe(false);
		}
	});

	it("does not match sibling directory names (.pi/agent-backup etc.)", () => {
		expect(checkProtectedBashCommand(AGENT_DIR, "rm -rf ~/.pi/agent-backup").prohibited).toBe(false);
		expect(checkProtectedBashCommand(AGENT_DIR, "rm -rf ~/.pi/agents").prohibited).toBe(false);
	});
});

describe("protected-config: recordProtectedBlockTrace", () => {
	it("appends a [PROTECTED_CONFIG] line to the worker task's trace.log", () => {
		const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mw-protected-config-"));
		try {
			const taskPath = path.join(dir, "task.md");
			recordProtectedBlockTrace("bash", "rm ~/.pi/agent/auth.json\nsecond line", taskPath);
			const trace = fs.readFileSync(path.join(dir, "trace.log"), "utf8");
			expect(trace).toContain("[PROTECTED_CONFIG]");
			expect(trace).toContain("tool=bash");
			expect(trace).toContain("target=rm ~/.pi/agent/auth.json");
			expect(trace).not.toContain("second line");
		} finally {
			fs.rmSync(dir, { recursive: true, force: true });
		}
	});

	it("is a no-op without a worker task env", () => {
		const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mw-protected-config-"));
		try {
			recordProtectedBlockTrace("bash", "rm ~/.pi/agent/auth.json", undefined);
			expect(fs.existsSync(path.join(dir, "trace.log"))).toBe(false);
		} finally {
			fs.rmSync(dir, { recursive: true, force: true });
		}
	});
});
