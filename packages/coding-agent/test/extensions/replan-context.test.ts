import { Check } from "typebox/value";
import { describe, expect, it } from "vitest";
import type { ExtensionAPI, ToolDefinition } from "../../src/core/extensions/types.ts";
import { registerReplanTool } from "../../src/extensions/agent-team-loop/pm/replan.ts";

describe("replan inventory pagination", () => {
	it("exposes bounded inventory paging and rejects bulk requests", () => {
		const tools: ToolDefinition[] = [];
		registerReplanTool(
			{ registerTool: (tool: ToolDefinition) => tools.push(tool) } as unknown as ExtensionAPI,
			".",
			() => "self",
		);
		const tool = tools[0];
		if (!tool) throw new Error("replan tool missing");
		const base = { operation: "inspect", key: "demo" };
		expect(Check(tool.parameters, base)).toBe(true);
		expect(Check(tool.parameters, { ...base, section: "cards", offset: 20, limit: 50 })).toBe(true);
		for (const invalid of [{ limit: 0 }, { limit: 51 }, { offset: -1 }, { offset: 0.5 }, { section: "all" }]) {
			expect(Check(tool.parameters, { ...base, ...invalid })).toBe(false);
		}
	});
});
