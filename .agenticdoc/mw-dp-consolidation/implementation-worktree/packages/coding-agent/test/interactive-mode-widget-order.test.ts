/**
 * mw-widget-order-stability: extension widgets must have a stable, declarable
 * order. The regression this locks: `setExtensionWidget` used to delete then
 * re-add the map entry on every refresh, so two pollers with different beats
 * (autopilot monitor + mw-watch, both belowEditor) flipped positions every few
 * seconds. The fix replaces in place (Map.set keeps the iteration position) and
 * sorts by an explicit `order`.
 */
import { describe, expect, test, vi } from "vitest";
import { Container } from "../../tui/src/tui.ts";
import { InteractiveMode } from "../src/modes/interactive/interactive-mode.ts";

type FakeThis = {
	extensionWidgetsAbove: Map<string, unknown>;
	extensionWidgetsBelow: Map<string, unknown>;
	extensionWidgetOrder: Map<string, number>;
	widgetContainerAbove: Container;
	widgetContainerBelow: Container;
	ui: { requestRender: () => void };
	renderWidgets: () => void;
	renderWidgetContainer: (...args: unknown[]) => void;
};

function fixture(): FakeThis {
	return {
		extensionWidgetsAbove: new Map(),
		extensionWidgetsBelow: new Map(),
		extensionWidgetOrder: new Map(),
		widgetContainerAbove: new Container(),
		widgetContainerBelow: new Container(),
		ui: { requestRender: vi.fn() },
		renderWidgets: (InteractiveMode as never as { prototype: FakeThis }).prototype.renderWidgets,
		renderWidgetContainer: (InteractiveMode as never as { prototype: FakeThis }).prototype.renderWidgetContainer,
	};
}

const setWidget = (InteractiveMode as never as { prototype: { setExtensionWidget: (...a: unknown[]) => void } })
	.prototype.setExtensionWidget;

function renderedBelow(self: FakeThis): string[] {
	return self.widgetContainerBelow.children.flatMap((child) => child.render(80).map((line) => line.trim()));
}

describe("InteractiveMode.setExtensionWidget ordering", () => {
	test("explicit order wins over registration order (monitor above watch)", () => {
		const self = fixture();
		// Adversarial registration order: the watch registers first.
		setWidget.call(self, "watch", ["watch-1"], { placement: "belowEditor", order: 10 });
		setWidget.call(self, "monitor", ["monitor-1"], { placement: "belowEditor", order: 0 });
		expect(renderedBelow(self)).toEqual(["monitor-1", "watch-1"]);
	});

	test("a refresh never reorders: replacing in place keeps the position", () => {
		const self = fixture();
		setWidget.call(self, "monitor", ["monitor-1"], { placement: "belowEditor", order: 0 });
		setWidget.call(self, "watch", ["watch-1"], { placement: "belowEditor", order: 10 });
		setWidget.call(self, "watch", ["watch-2"], { placement: "belowEditor", order: 10 });
		setWidget.call(self, "monitor", ["monitor-2"], { placement: "belowEditor", order: 0 });
		expect(renderedBelow(self)).toEqual(["monitor-2", "watch-2"]);
	});

	test("equal order keeps registration order", () => {
		const self = fixture();
		setWidget.call(self, "a", ["a"], { placement: "belowEditor" });
		setWidget.call(self, "b", ["b"], { placement: "belowEditor" });
		setWidget.call(self, "a", ["a2"], { placement: "belowEditor" });
		expect(renderedBelow(self)).toEqual(["a2", "b"]);
	});

	test("undefined content clears the widget and its order", () => {
		const self = fixture();
		setWidget.call(self, "monitor", ["monitor-1"], { placement: "belowEditor", order: 0 });
		setWidget.call(self, "monitor", undefined, { placement: "belowEditor", order: 0 });
		expect(self.extensionWidgetsBelow.has("monitor")).toBe(false);
		expect(self.extensionWidgetOrder.has("monitor")).toBe(false);
		expect(renderedBelow(self)).toEqual([]);
	});

	test("a placement change moves the widget and disposes the old entry", () => {
		const self = fixture();
		setWidget.call(self, "x", ["x"], { placement: "belowEditor", order: 0 });
		setWidget.call(self, "x", ["x"], { placement: "aboveEditor", order: 0 });
		expect(self.extensionWidgetsBelow.has("x")).toBe(false);
		expect(self.extensionWidgetsAbove.has("x")).toBe(true);
		expect(renderedBelow(self)).toEqual([]);
	});
});
