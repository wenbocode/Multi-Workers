/**
 * shared/card-digest.ts — EOL-normalized sha256 for dispatch cards (T-02,
 * key `mw-dispatch-card-gate`, AC-006).
 *
 * The `card_sha256:` header written into every generated `task.md` must be
 * comparable with the Python side (`packages/multi-workers/mw_common.py::
 * sha256_eol_normalized`), so the recipe is frozen here byte-for-byte:
 * CRLF → LF on the raw bytes, then sha256 of the result. A line-ending flip
 * on checkout (core.autocrlf) is therefore not drift, while an equal-length
 * content substitution is.
 *
 * Leaf module: `node:crypto` + `node:fs` only, no project imports, no
 * project-root guessing — the caller passes a resolved path.
 */
/**
 * CRLF → LF over raw bytes, the exact `data.replace(b"\r\n", b"\n")` recipe of
 * `mw_common.sha256_eol_normalized`. A latin1 round-trip is byte-preserving
 * for every 0x00–0xFF value, so the replacement never touches multi-byte UTF-8
 * sequences (each of their bytes is >= 0x80) and lone `\r` bytes stay put, just
 * like Python's `bytes.replace`.
 */
export declare function eolNormalizeBytes(data: Uint8Array): Buffer;
/** EOL-normalized sha256 of an in-memory byte range (hex). */
export declare function sha256EolNormalizedBytes(data: Uint8Array): string;
/**
 * EOL-normalized sha256 of a card file (hex). Throws when the file is
 * unreadable — callers gate on `readEnvelope` first, which reports the missing
 * file as `missing: ["file"]` before a digest is ever needed.
 */
export declare function cardDigest(cardPath: string): string;
//# sourceMappingURL=card-digest.d.ts.map