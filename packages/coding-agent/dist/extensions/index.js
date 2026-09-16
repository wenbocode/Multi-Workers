import agentTeamLoop from "./agent-team-loop/index.js";
import llamaExtension from "./llama/index.js";
export const builtInExtensions = [
    { name: "llama.cpp", factory: llamaExtension, hidden: true },
    { name: "agent-team-loop", factory: agentTeamLoop },
];
//# sourceMappingURL=index.js.map