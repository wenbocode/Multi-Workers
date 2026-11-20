import { listGates, readConfig, readRoadmap } from "../autopilot/status-model.ts";
import { gateApprovalRow } from "../shared/decide-policy.ts";

export const PM_GATE_ROUTING_RULE =
	"Use dp-gate-approve only for the action named by an existing pending framework gate in the claimed key or its stage. " +
	"Use its gate ID as the trigger. A build, deployment, readiness check, or dp-route suggestion alone does not create a gate. " +
	"Ordinary work follows its recorded authorization, workspace rules and hard checks.";

interface GateRoute {
	status: "not-applicable" | "state-unavailable" | "framework-gate";
	instruction: string;
	gate_id?: string;
	kind?: string;
	blocker?: "automation-inactive" | "p0-disabled";
}

/** Routing advice only. The framework gate handler owns authorization and effects. */
export function resolvePmGateRoute(projectDir: string, key: string, trigger: string): GateRoute {
	const { gates, errors } = listGates(projectDir);
	if (errors.length) {
		return {
			status: "state-unavailable",
			instruction: "Cannot verify the gate queue. Inspect mw autopilot gates --json before resolving this gate.",
		};
	}
	const absent: GateRoute = {
		status: "not-applicable",
		instruction:
			"No matching pending framework gate for this trigger and key. Evaluate the action using its recorded authorization and project checks. This lookup grants no permission.",
	};
	const gate = gates.find((entry) => entry.id === trigger);
	if (
		!gate ||
		gate.status !== "pending" ||
		(gate.decision && gate.decision.transport !== "pending") ||
		(gate.key !== null && gate.key !== key)
	)
		return absent;
	if (gate.key === null) {
		const roadmap = readRoadmap(projectDir);
		if (gate.stage === null || !roadmap.ok || roadmap.warnings.length) {
			return {
				status: "state-unavailable",
				instruction: "Cannot verify the scope of this keyless gate. Inspect its framework record and roadmap.",
			};
		}
		if (!roadmap.stages.some((stage) => stage.number === gate.stage && stage.keys.some((row) => row.key === key)))
			return absent;
	}
	const identity = { gate_id: gate.id, kind: gate.kind };
	const config = readConfig(projectDir);
	if (!config.ok)
		return {
			...identity,
			status: "state-unavailable",
			instruction: "Cannot verify the Autopilot configuration. Keep the gate pending.",
		};
	if (!config.config.enabled || config.config.paused || config.config.auto_gate_mode !== "live") {
		return {
			...identity,
			status: "framework-gate",
			blocker: "automation-inactive",
			instruction: "This framework gate remains pending. Automated gate handling is inactive.",
		};
	}
	const row = gateApprovalRow(projectDir);
	if (row === "unreadable")
		return {
			...identity,
			status: "state-unavailable",
			instruction: "Cannot verify the P0 authorization row. Keep the gate pending.",
		};
	if (row === "off")
		return {
			...identity,
			status: "framework-gate",
			blocker: "p0-disabled",
			instruction: "The P0 decision point is disabled. Keep this gate pending.",
		};
	return {
		status: "framework-gate",
		...identity,
		instruction:
			"Inspect this gate with mw autopilot gates --json and use its framework handler for the recorded action. Keep the action gated until that handler authorizes it. A generic decision or user-supplied receipt cannot release it.",
	};
}
