"use strict";
const byId = (id) => document.getElementById(id);
const decoder = new TextDecoder("utf-8", { fatal: true });
let selection = null;
function encode(bytes) {
	let text = "";
	for (const byte of bytes) text += String.fromCharCode(byte);
	return btoa(text);
}
const decode = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
const safeText = (text) => text.replace(/[\u0000-\u001f\u007f-\u009f\u00ad\u034f\u061c\u180e\u200b-\u200f\u2028-\u202e\u2060-\u206f\ufeff]/gu,
	(c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
async function post(route, body = {}) {
	const response = await fetch("/api/" + route, {
		method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), cache: "no-store",
	});
	const result = await response.json();
	if (!response.ok || !result.ok) throw Error(result.reason || "Request refused");
	return result;
}
function run(fn) {
	return async () => {
		try { await fn(); } catch (error) { byId("status").textContent = error.message; }
	};
}
async function refresh() {
	const data = await post("list");
	selection = null;
	byId("review").hidden = true;
	byId("requests").replaceChildren();
	for (const op of data.operations) {
		const entry = document.createElement("li"), button = document.createElement("button");
		button.textContent = op.project + " " + op.op + " " + op.id;
		button.onclick = run(() => display(op.id));
		entry.append(button); byId("requests").append(entry);
	}
	for (const [id, values] of [["project", data.projects], ["kind", data.roles.filter((r) => r !== "ask")]]) {
		const select = byId(id); select.replaceChildren();
		for (const value of values) select.add(new Option(value, value));
	}
	byId("records").textContent = safeText(JSON.stringify({ candidates: data.candidates, bindings: data.bindings, grants: data.grants }, null, 2));
	byId("status").textContent = "Pending requests: " + data.operations.length;
}
async function display(id) {
	const data = await post("display", { id });
	const bytes = decode(data.payload_b64);
	const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), x => x.toString(16).padStart(2,"0")).join("");
	if (digest !== data.sha256) throw Error("Payload hash mismatch");
	selection = { id, sha256: digest };
	const content = decoder.decode(bytes);
	byId("purpose").textContent = data.project + " | " + data.purpose + " | " + id;
	byId("provenance").textContent = data.purpose === "ask"
		? "Draft supplied by MW. Approve only after checking every character, path and boundary."
		: "Protected request frozen by the operator host.";
	byId("content").value = content;
	byId("content").readOnly = data.purpose !== "ask";
	byId("escaped").textContent = safeText(content);
	byId("digest").textContent = "SHA-256 " + digest;
	byId("save").hidden = data.purpose !== "ask";
	byId("approve").disabled = false;
	byId("review").hidden = false;
}
byId("content").oninput = () => { byId("approve").disabled = true; };
byId("save").onclick = run(async () => {
	const request = selection;
	await post("edit", { ...request, payload_b64: encode(new TextEncoder().encode(byId("content").value)) });
	await display(request.id);
	byId("provenance").textContent = "Edited locally; the previous confirmation is void and the bytes were frozen again.";
});
byId("approve").onclick = run(async () => {
	const request = selection;
	byId("approve").disabled = true;
	const {options} = await post("challenge", request);
	const publicKey = PublicKeyCredential.parseRequestOptionsFromJSON(options.publicKey);
	const credential = await navigator.credentials.get({ publicKey });
	if (request !== selection || !credential) throw Error("Request changed or cancelled");
	const result = await post("confirm", { ...request, assertion: credential.toJSON() });
	await refresh();
	byId("status").textContent = "Operation " + result.id + " | " + result.state;
});
byId("cancel").onclick = run(async () => { await post("cancel", selection); await refresh(); });
byId("propose").onclick = run(async () => {
	const result = await post("propose", {project_id: byId("project").value, op: byId("kind").value, terms: JSON.parse(byId("terms").value)});
	await refresh(); await display(result.id);
});
byId("refresh").onclick = run(refresh);
run(refresh)();
