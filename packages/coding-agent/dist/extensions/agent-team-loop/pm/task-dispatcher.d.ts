import { type WorkerEntry, type WorkerStore } from "../shared/worker-store.ts";
import { type WriteFaceRejectCode } from "../shared/write-face.ts";
export declare function dispatchTask(entry: Omit<WorkerEntry, "dispatchedAt" | "updatedAt">, store: WorkerStore): Promise<DispatchOutcome>;
/** Stable PM-side refusal codes. `write-face-overlap` / `write-face-undeclared`
 * are the conductor's codes (`dispatch.py:1173/1198/1208`); the remaining
 * values are the parse-time codes the shared operator emits, which the
 * conductor refuses with the same code (`dispatch.py:1164`). */
export type DispatchRefusalCode = "write-face-overlap" | "write-face-undeclared" | WriteFaceRejectCode;
/** A zero-side-effect dispatch refusal / D-003 deferral (D-008). The PM audit
 * channel is this return value (the conductor writes `timeline.jsonl`). */
export interface DispatchRefusal {
    ok: false;
    code: DispatchRefusalCode;
    /** `overlap-with:<task_key>` payload (overlap refusals only). */
    overlapWith?: string;
    /** Lexically-provable conflict sample path (provable overlap only). */
    sample?: string;
    /** D-003: serial-only deferral, not an invalid task. */
    serialOnly?: boolean;
    /** Number of same-owner in-flight workers (undeclared deferral only). */
    inFlight?: number;
    /** Machine reason, byte-identical to the conductor's `DispatchResult.reason`. */
    reason: string;
    /** Human audit line, byte-identical to the conductor's timeline detail. */
    detail: string;
}
/** The PM dispatch result: `{ ok: true }` queued (or idempotently re-queued);
 * a {@link DispatchRefusal} wrote nothing. */
export type DispatchOutcome = {
    ok: true;
} | DispatchRefusal;
/** Base for every write-face parse: the `.agenticdoc` parent — the same root
 * `WorkerStore` anchors its queue under. Given at the call site, never
 * inferred inside the operator (D-006/AC-007; mirrors
 * `dispatch.py::write_face_base`). */
export declare function writeFaceBase(agenticdocRoot: string): string;
/** Explicit case mode for the write-face operator (D-006/AC-007): mirrors
 * `dispatch.py::write_face_case_insensitive` (`os.name == "nt"`). */
export declare function writeFaceCaseInsensitive(): boolean;
//# sourceMappingURL=task-dispatcher.d.ts.map