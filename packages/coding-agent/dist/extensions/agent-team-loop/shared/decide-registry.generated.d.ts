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
/** How an entry's answer enum is produced (`decision_points.ENTRY_KINDS`). */
export type DecideRegistryEntryKind = "fixed" | "dynamic-candidates" | "route-targets";
/** Role eligible to *initiate* an entry: eligibility only, never a grant. */
export type DecideRegistryRoleScope = "pm" | "worker";
/**
 * The PM-prepared basis layer (D-012A). Independent of the business
 * material and never carried by the trimmable `context` block: a basis
 * that could be cut away would leave an invalid request looking valid.
 */
export interface DecideRegistryPreparation {
    /** Exact keys of the local `preparation` block. */
    keys: string[];
    /** Exact keys of one `basis_catalog` item. */
    basisItemKeys: string[];
    /** Who prepares the catalog (a real PM window, never a self-reported role). */
    basisSource: string;
    /** This layer is never derived from or merged into the business material. */
    independentOf: string;
    /** The one basis field the model allowlist allows besides the material. */
    basisStateField: string;
    /** Core evidence: never carried by the trimmable `context` block. */
    contextTrimmable: false;
}
/** Required/optional dp state fields, role, model allowlist, context slots and preparation layering, generated from the Python registry. */
export interface DecideRegistryEntry {
    questionsVersion: string;
    businessQuestionId: string;
    /** Allowed fixed answer IDs. Dynamic entries resolve candidates from the request material. */
    fixedChoiceIds: readonly string[];
    kind: DecideRegistryEntryKind;
    roleScope: DecideRegistryRoleScope;
    requiredStateFields: DecideRegistryField[];
    optionalStateFields: DecideRegistryField[];
    /** Exact business keys sent to the model (every active entry declares one; absent = no allowlist). */
    modelStateFields?: string[];
    /** The only trimmable block this entry may emit: `fit_context` may cut whole slots, so core evidence is never a slot. */
    contextSlots: string[];
    preparation: DecideRegistryPreparation;
}
/** One read-only retirement record (never entry-shaped, never callable). */
export interface DecideRegistryRetiredEntry {
    id: string;
    tier: string;
    description: string;
    disposition: "migrated" | "retired";
    migratedTo: string | null;
    note: string;
}
export declare const DECIDE_REGISTRY_PREPARATION: DecideRegistryPreparation;
/** Exactly the eight active entries, in registry order. */
export declare const DECIDE_REGISTRY: Record<string, DecideRegistryEntry>;
/**
 * The retired ids, read-only: disposition, migration target and the
 * explanation a reader (or a refusal) may quote. No required/model field
 * contract, no entry-shaped key -- never an alias, never a second menu.
 */
export declare const DECIDE_REGISTRY_RETIRED: DecideRegistryRetiredEntry[];
//# sourceMappingURL=decide-registry.generated.d.ts.map