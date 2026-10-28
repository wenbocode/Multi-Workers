/** JSON-native state field kinds the registry can declare. */
export type DecideRegistryFieldType = "string" | "integer" | "number" | "boolean" | "array" | "object";
/**
 * One declared dp state field. `type`/`description` are always present;
 * every other property is a declared constraint (T04 typed contract).
 */
export interface DecideRegistryField {
    name: string;
    type: DecideRegistryFieldType;
    description: string;
    enum?: readonly string[];
    maxItems?: number;
    itemType?: DecideRegistryFieldType;
    maxBytes?: number;
    itemMaxBytes?: number;
    signed?: boolean;
    minValue?: number;
    emptyIsValue?: boolean;
}
/** Required/optional dp state fields + model allowlist + context slots, generated from the Python registry. */
export interface DecideRegistryEntry {
    questionsVersion: string;
    requiredStateFields: DecideRegistryField[];
    optionalStateFields: DecideRegistryField[];
    /** Exact business keys sent to the model; absent = no allowlist (legacy dp unchanged). */
    modelStateFields?: string[];
    contextSlots: string[];
}
export declare const DECIDE_REGISTRY: Record<string, DecideRegistryEntry>;
//# sourceMappingURL=decide-registry.generated.d.ts.map