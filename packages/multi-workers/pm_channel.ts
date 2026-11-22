/** Run with Node 24+. No Codex CLI or provider call is involved. */
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { parseArgs } from "node:util";
import { PmChannel, parsePmStageGrant } from "../coding-agent/src/extensions/agent-team-loop/pm/codex-channel.ts";
import { lockDutyTarget } from "./pm_duty_lease.ts";

try {
	const { values, positionals } = parseArgs({
		allowPositionals: true,
		options: { project: { type: "string", default: "." }, key: { type: "string" }, binding: { type: "string" },
			id: { type: "string" }, file: { type: "string" }, text: { type: "string" }, "stage-file": { type: "string" } },
	});
	const [action] = positionals;
	const { project, key, binding, id, file, text } = values;
	const stageFile = values["stage-file"];
	if (stageFile !== undefined && action !== "send") throw new Error("--stage-file is only valid for send");
	if (!key || positionals.length !== 1) throw new Error("Expected status|send|receipt --project DIR --key KEY");
	const channel = new PmChannel(project);
	let result: object;
	if (action === "status") result = channel.status(key);
	else if (action === "send" && binding && (file !== undefined) !== (text !== undefined)) {
		const thread = process.env.CODEX_THREAD_ID;
		if (!thread || !/^[a-f0-9-]{36}$/i.test(thread) || process.env.PI_WORKER_TASK !== undefined)
			throw new Error("Send from the current Codex desktop chat");
		const body = file !== undefined ? readFileSync(file, "utf8") : text ?? "";
		if (!body.trim()) throw new Error("Empty message");
		const stage = stageFile === undefined ? undefined : parsePmStageGrant(JSON.parse(readFileSync(stageFile, "utf8")) as unknown);
		if (stage !== undefined && !stage.ok) throw new Error(`Invalid typed stage grant: ${stage.gaps.join(",")}`);
		const lease = await lockDutyTarget(channel.dir, key, "send");
		try {
			result = channel.send(key, binding, id ?? randomUUID(), `Codex chat ${thread}\n${body}`, undefined, stage?.ok ? stage.value : undefined);
		} finally { lease.close(); }
	} else if (action === "receipt" && binding && id) result = channel.receipt(key, binding, id);
	else throw new Error("send requires --binding UUID and --file PATH or --text TEXT; receipt requires --binding UUID --id UUID");
	console.log(JSON.stringify(result));
} catch (error) {
	console.error(JSON.stringify({ error: error instanceof Error ? error.message : String(error) }));
	process.exitCode = 1;
}
