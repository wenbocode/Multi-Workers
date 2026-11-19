import { createHash } from "node:crypto";
import { createServer, type Server } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";

export async function lockDutyTarget(
	channelDirectory: string,
	key: string,
	use: "monitor" | "send" = "monitor",
): Promise<Server> {
	const token = createHash("sha256")
		.update(JSON.stringify([channelDirectory, key.trim().toLowerCase(), use]))
		.digest("hex")
		.slice(0, 32);
	const path =
		process.platform === "win32"
			? `\\\\.\\pipe\\mw-shift-${token}`
			: process.platform === "linux"
				? `\0mw-shift-${token}`
				: join(tmpdir(), `mw-shift-${token}.sock`);
	const server = createServer((socket) => socket.end());
	await new Promise<void>((ok, fail) => {
		server.once("error", fail);
		server.listen(path, ok);
	});
	return server;
}
