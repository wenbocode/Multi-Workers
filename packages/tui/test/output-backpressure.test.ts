import assert from "node:assert/strict";
import { Writable } from "node:stream";
import { describe, it } from "node:test";
import { setImmediate, setTimeout } from "node:timers/promises";
import { ProcessTerminal } from "../src/terminal.ts";
import { TuiMainScreen } from "../src/tui-main-screen.ts";

function stalledOutput() {
	let blocked = true;
	let finishWrite: (() => void) | undefined;
	const writes: string[] = [];
	const output = new Writable({
		decodeStrings: false,
		highWaterMark: 1,
		write(chunk: string, _encoding, callback) {
			writes.push(chunk);
			if (blocked) finishWrite = callback;
			else callback();
		},
	});
	const descriptor = Object.getOwnPropertyDescriptor(process, "stdout")!;
	Object.defineProperty(process, "stdout", { configurable: true, value: output });
	const terminal = new ProcessTerminal();
	const tui = new TuiMainScreen(terminal);
	let state = "initial";
	tui.addChild({
		render: () => Array.from({ length: 1000 }, (_, i) => `${state} line ${i}`),
		invalidate() {},
	});
	return {
		output,
		tui,
		writes,
		setState(value: string) {
			state = value;
		},
		resume() {
			blocked = false;
			finishWrite?.();
			finishWrite = undefined;
		},
		cleanup() {
			tui.stop({ preserveScreen: true });
			output.destroy();
			Object.defineProperty(process, "stdout", descriptor);
		},
	};
}

describe("TUI output backpressure", () => {
	it("bounds queued redraws and paints the latest state after the stream drains", async () => {
		const harness = stalledOutput();
		try {
			harness.tui.renderNow();
			const queued = harness.output.writableLength;
			assert.ok(harness.output.writableNeedDrain);
			for (let i = 0; i < 200; i++) {
				harness.setState(`update ${i}`);
				harness.tui.requestRender(i % 2 === 0);
				await setImmediate();
			}
			assert.equal(harness.output.writableLength, queued);
			assert.equal(harness.output.listenerCount("drain"), 1);
			assert.equal(harness.tui.fullRedraws, 1);
			harness.resume();
			await setTimeout(40);
			assert.equal(harness.output.writableLength, 0);
			assert.equal(harness.output.listenerCount("drain"), 0);
			assert.equal(harness.tui.fullRedraws, 2);
			assert.ok(harness.writes.join("").includes("update 199 line 999"));
			assert.ok(!harness.writes.join("").includes("update 198 line 999"));
		} finally {
			harness.cleanup();
		}
	});

	it("defers immediate redraws too", async () => {
		const harness = stalledOutput();
		try {
			harness.tui.renderNow();
			const queued = harness.output.writableLength;
			for (let i = 0; i < 200; i++) {
				harness.setState(`immediate ${i}`);
				harness.tui.renderNow(true);
			}
			assert.equal(harness.output.writableLength, queued);
			assert.equal(harness.output.listenerCount("drain"), 1);
			harness.resume();
			await setTimeout(40);
			assert.ok(harness.writes.join("").includes("immediate 199 line 999"));
		} finally {
			harness.cleanup();
		}
	});

	it("removes the drain listener on stop and does not redraw after shutdown", async () => {
		const harness = stalledOutput();
		try {
			harness.tui.renderNow();
			harness.tui.requestRender(true);
			await setImmediate();
			assert.equal(harness.output.listenerCount("drain"), 1);
			harness.tui.stop({ preserveScreen: true });
			harness.tui.renderNow(true);
			harness.tui.requestRender(true);
			assert.equal(harness.output.listenerCount("drain"), 0);
			harness.resume();
			await setTimeout(40);
			assert.equal(harness.tui.fullRedraws, 1);
		} finally {
			harness.cleanup();
		}
	});
});
