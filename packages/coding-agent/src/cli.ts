#!/usr/bin/env node
/**
 * CLI entry point for the refactored coding agent.
 * Uses main.ts with AgentSession and new mode modules.
 *
 * Test with: npx tsx src/cli-new.ts [args...]
 */
import { APP_NAME } from "./config.ts";
import { configureHttpDispatcher } from "./core/http-dispatcher.ts";
import { main } from "./main.ts";

// Claim the console title only when this process owns the terminal. On Windows
// `process.title` is SetConsoleTitleW on the console we inherited, so a child
// invocation with piped stdout (mw's `pi --list-models` capability probe, worker
// spawns, RPC) would rename the parent pi window to "pi" and the TUI would not
// take its own title back (mw-console-title-clobber). Interactive runs are
// unaffected: their stdout is the terminal.
if (process.stdout.isTTY) {
	process.title = APP_NAME;
}
process.env.PI_CODING_AGENT = "true";
process.env.AI_AGENT = "pi";
process.emitWarning = (() => {}) as typeof process.emitWarning;

// Configure undici's global dispatcher before provider SDKs issue requests.
// Runtime settings are applied once SettingsManager has loaded global/project settings.
configureHttpDispatcher();

main(process.argv.slice(2));
