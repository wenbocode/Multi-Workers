import { uuidv7 } from "@earendil-works/pi-ai";
import { Session } from "./session.js";
import { SessionError, } from "./types.js";
function* ordered(items, order) {
    if (order === "oldestFirst") {
        yield* items;
        return;
    }
    for (let index = items.length - 1; index >= 0; index--)
        yield items[index];
}
function provisionEntry(newEntry, parentId, seq) {
    // Object spread does not preserve the correlation between a discriminant and the rest of a union member.
    return { ...newEntry, parentId, seq, timestamp: Date.now() };
}
function provisionRecord(newRecord, seq) {
    // Object spread does not preserve the correlation between a discriminant and the rest of a union member.
    return { ...newRecord, seq, timestamp: Date.now() };
}
export class InMemorySessionStorage {
    metadata;
    sequence = 0;
    usedIds = new Set();
    entries = [];
    entriesById = new Map();
    records = [];
    openOperationsByLane = new Map();
    lanes = new Map([["main", null]]);
    log = [];
    stats = {
        messageCount: 0,
        cachedTokens: 0,
        uncachedTokens: 0,
        totalTokens: 0,
        costTotal: 0,
    };
    name;
    labels = new Map();
    constructor(metadata) {
        this.metadata = structuredClone(metadata);
    }
    fork(metadata, options) {
        const storage = new InMemorySessionStorage(metadata);
        let copiedEntries;
        if (options.scope === "tree") {
            copiedEntries = this.entries;
            storage.lanes.clear();
            for (const [lane, leafId] of this.lanes)
                storage.lanes.set(lane, leafId);
        }
        else {
            const selectedEntryId = options.entryId ?? this.lanes.get("main") ?? null;
            let targetId = null;
            if (selectedEntryId !== null) {
                const target = this.entriesById.get(selectedEntryId);
                if (!target || target.type !== "message") {
                    throw new SessionError("invalid_fork_target", `Fork target is not a message entry: ${selectedEntryId}`);
                }
                const position = options.position ?? (options.entryId === undefined ? "at" : "before");
                targetId = position === "at" ? target.id : target.parentId;
            }
            copiedEntries = [...this.walkToRoot(targetId)].reverse();
            storage.lanes.set("main", targetId);
        }
        const copiedIds = new Set(copiedEntries.map((entry) => entry.id));
        for (const sourceEntry of copiedEntries) {
            const entry = structuredClone(sourceEntry);
            entry.seq = storage.nextSequence();
            storage.entries.push(entry);
            storage.entriesById.set(entry.id, entry);
            storage.usedIds.add(entry.id);
            storage.log.push({ kind: "entry", seq: entry.seq, entry });
            if (entry.type === "message")
                storage.stats.messageCount += 1;
        }
        for (const [lane, leafId] of options.scope === "tree" ? this.lanes : []) {
            storage.log.push({ kind: "lane", seq: storage.nextSequence(), lane, leafId });
        }
        if (this.name !== undefined) {
            storage.name = this.name;
            storage.log.push({ kind: "fact", seq: storage.nextSequence(), fact: "name", name: this.name });
        }
        for (const [targetId, label] of this.labels) {
            if (!copiedIds.has(targetId))
                continue;
            storage.labels.set(targetId, label);
            storage.log.push({ kind: "fact", seq: storage.nextSequence(), fact: "label", targetId, label });
        }
        return storage;
    }
    async getMetadata() {
        return structuredClone(this.metadata);
    }
    async getLanes() {
        return [...this.lanes].map(([lane, leafId]) => ({ lane, leafId }));
    }
    async createLane(lane, at) {
        if (this.lanes.has(lane))
            throw new SessionError("already_exists", `Lane already exists: ${lane}`);
        this.validateTarget(at);
        this.lanes.set(lane, at);
        this.log.push({ kind: "lane", seq: this.nextSequence(), lane, leafId: at });
    }
    async moveLane(lane, to) {
        this.requireLane(lane);
        this.validateTarget(to);
        this.lanes.set(lane, to);
        this.log.push({ kind: "lane", seq: this.nextSequence(), lane, leafId: to });
    }
    async appendEntry(newEntry, lane) {
        const parentId = this.requireLane(lane);
        this.validateUnusedId(newEntry.id);
        const clonedEntry = structuredClone(newEntry);
        const entry = provisionEntry(clonedEntry, parentId, this.nextSequence());
        this.usedIds.add(entry.id);
        this.entries.push(entry);
        this.entriesById.set(entry.id, entry);
        this.lanes.set(lane, entry.id);
        this.log.push({ kind: "entry", seq: entry.seq, entry });
        if (entry.type === "message")
            this.stats.messageCount += 1;
        return structuredClone(entry);
    }
    async appendRecord(newRecord) {
        this.requireLane(newRecord.lane);
        this.validateUnusedId(newRecord.id);
        const clonedRecord = structuredClone(newRecord);
        const record = provisionRecord(clonedRecord, this.nextSequence());
        this.usedIds.add(record.id);
        this.records.push(record);
        // Maintain the recovery projection incrementally so restore never scans the full record log.
        if (record.type === "operation_started") {
            let openOperations = this.openOperationsByLane.get(record.lane);
            if (!openOperations) {
                openOperations = new Map();
                this.openOperationsByLane.set(record.lane, openOperations);
            }
            openOperations.set(record.id, record);
        }
        else if (record.type === "operation_finished") {
            this.openOperationsByLane.get(record.lane)?.delete(record.runId);
        }
        this.log.push({ kind: "record", seq: record.seq, record });
        if (record.type === "usage") {
            this.stats.cachedTokens += record.usage.cacheRead;
            this.stats.uncachedTokens += record.usage.input + record.usage.cacheWrite;
            this.stats.totalTokens += record.usage.totalTokens;
            this.stats.costTotal += record.usage.cost.total;
        }
        return structuredClone(record);
    }
    async getEntry(id) {
        const entry = this.entriesById.get(id);
        return entry === undefined ? undefined : structuredClone(entry);
    }
    async findEntries(query = {}) {
        const results = [];
        for (const entry of ordered(this.entries, query.order)) {
            if (!this.matchesEntryQuery(entry, query))
                continue;
            results.push(entry);
            if (results.length === query.limit)
                break;
        }
        return structuredClone(results);
    }
    async findEntriesOnBranch(query) {
        const results = [];
        if (query.order === "oldestFirst") {
            for (const entry of [...this.walkToRoot(query.start)].reverse()) {
                const reachedBound = entry.id === query.stopAtId || entry.type === query.stopAtType;
                if (this.matchesEntryQuery(entry, query))
                    results.push(entry);
                if (reachedBound || results.length === query.limit)
                    break;
            }
        }
        else {
            for (const entry of this.walkToRoot(query.start, query)) {
                if (this.matchesEntryQuery(entry, query))
                    results.push(entry);
                if (results.length === query.limit)
                    break;
            }
        }
        return structuredClone(results);
    }
    async findRecords(query = {}) {
        const results = [];
        for (const record of ordered(this.records, query.order)) {
            if (!this.matchesRecordQuery(record, query))
                continue;
            results.push(record);
            if (results.length === query.limit)
                break;
        }
        return structuredClone(results);
    }
    async findOpenOperations(lane, options) {
        const openOperationsById = this.openOperationsByLane.get(lane);
        const openOperations = openOperationsById ? [...openOperationsById.values()].reverse() : [];
        return structuredClone(options?.limit === undefined ? openOperations : openOperations.slice(0, options.limit));
    }
    async getLog(options = {}) {
        const results = [];
        for (const item of this.log) {
            if (options.afterSeq !== undefined && item.seq <= options.afterSeq)
                continue;
            results.push(item);
            if (results.length === options.limit)
                break;
        }
        return structuredClone(results);
    }
    async getName() {
        return this.name;
    }
    async setName(name) {
        this.name = name;
        this.log.push({ kind: "fact", seq: this.nextSequence(), fact: "name", name });
    }
    async getLabel(id) {
        return this.labels.get(id);
    }
    async setLabel(id, label) {
        this.validateTarget(id);
        if (label === undefined)
            this.labels.delete(id);
        else
            this.labels.set(id, label);
        this.log.push({ kind: "fact", seq: this.nextSequence(), fact: "label", targetId: id, label });
    }
    async getStats() {
        return structuredClone(this.stats);
    }
    nextSequence() {
        return ++this.sequence;
    }
    requireLane(lane) {
        const leafId = this.lanes.get(lane);
        if (leafId === undefined)
            throw new SessionError("invalid_lane", `Lane not found: ${lane}`);
        return leafId;
    }
    validateTarget(targetId) {
        if (targetId !== null && !this.entriesById.has(targetId)) {
            throw new SessionError("not_found", `Entry not found: ${targetId}`);
        }
    }
    validateUnusedId(id) {
        if (this.usedIds.has(id))
            throw new SessionError("already_exists", `Session id already exists: ${id}`);
    }
    *walkToRoot(start, bounds) {
        if (start === null)
            return;
        const visited = new Set();
        let current = this.entriesById.get(start);
        if (!current)
            throw new SessionError("not_found", `Entry not found: ${start}`);
        while (current) {
            if (visited.has(current.id)) {
                throw new SessionError("invalid_entry", `Session branch contains a cycle at ${current.id}`);
            }
            visited.add(current.id);
            yield current;
            if (current.id === bounds?.stopAtId || current.type === bounds?.stopAtType)
                break;
            if (current.parentId === null)
                break;
            const parentId = current.parentId;
            current = this.entriesById.get(parentId);
            if (!current)
                throw new SessionError("invalid_entry", `Entry not found: ${parentId}`);
        }
    }
    matchesEntryQuery(entry, query) {
        return ((query.type === undefined || entry.type === query.type) &&
            (query.customType === undefined || (entry.type === "custom" && entry.customType === query.customType)) &&
            (query.cursor === undefined ||
                (query.order === "oldestFirst" ? entry.seq > query.cursor.afterSeq : entry.seq < query.cursor.afterSeq)));
    }
    matchesRecordQuery(record, query) {
        return ((query.lane === undefined || record.lane === query.lane) &&
            (query.type === undefined || record.type === query.type) &&
            (query.runId === undefined ||
                (record.type === "operation_started"
                    ? record.id === query.runId
                    : "runId" in record && record.runId === query.runId)) &&
            (query.operationKind === undefined ||
                (record.type === "operation_started" && record.intent.kind === query.operationKind)) &&
            (query.afterSeq === undefined || record.seq > query.afterSeq));
    }
}
export class InMemorySessionRepo {
    sessions = new Map();
    async create(options = {}) {
        const id = options.id ?? uuidv7();
        if (this.sessions.has(id))
            throw new SessionError("already_exists", `Session already exists: ${id}`);
        const storage = new InMemorySessionStorage({
            id,
            createdAt: Date.now(),
            parentSessionId: options.parentSessionId,
        });
        this.sessions.set(id, storage);
        return new Session(storage);
    }
    async open(metadata) {
        return new Session(this.requireStorage(metadata.id));
    }
    async list() {
        return Promise.all([...this.sessions.values()].map((storage) => storage.getMetadata()));
    }
    async delete(metadata) {
        this.sessions.delete(metadata.id);
    }
    async fork(source, options = {}) {
        const sourceStorage = this.requireStorage(source.id);
        const id = options.id ?? uuidv7();
        if (this.sessions.has(id))
            throw new SessionError("already_exists", `Session already exists: ${id}`);
        const storage = sourceStorage.fork({ id, createdAt: Date.now(), parentSessionId: options.parentSessionId ?? source.id }, options);
        this.sessions.set(id, storage);
        return new Session(storage);
    }
    requireStorage(id) {
        const storage = this.sessions.get(id);
        if (!storage)
            throw new SessionError("not_found", `Session not found: ${id}`);
        return storage;
    }
}
//# sourceMappingURL=memory.js.map