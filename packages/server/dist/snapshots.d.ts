import { type EventEnvelope, type ModelMetadata, type ServerSnapshot, type SessionSummary } from "@earendil-works/pi-protocol";
import type { ConnectionState } from "./connection.ts";
import type { PiServerService } from "./types.ts";
interface ServerSnapshotPublisherOptions {
    serverId: string;
    service: PiServerService;
    connections: Set<ConnectionState>;
    isClosing: () => boolean;
    listSessions: (connection?: ConnectionState) => Promise<SessionSummary[]>;
    sendMessage: (connection: ConnectionState, message: EventEnvelope) => Promise<boolean>;
    reportError: (error: unknown) => void;
}
export declare class ServerSnapshotPublisher {
    private readonly options;
    private revision;
    private broadcastQueue;
    constructor(options: ServerSnapshotPublisherOptions);
    get currentRevision(): number;
    get(models?: ModelMetadata[], connection?: ConnectionState): Promise<ServerSnapshot>;
    broadcast(): Promise<void>;
    private performBroadcast;
}
export {};
//# sourceMappingURL=snapshots.d.ts.map