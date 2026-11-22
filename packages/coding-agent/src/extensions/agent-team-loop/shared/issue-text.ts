/**
 * shared/issue-text.ts — deterministic issue text boundaries.
 *
 * There are TWO distinct, explicitly selected string boundaries:
 *
 *  - RAW ingress (`textMode: "raw"`): an untrusted field is encoded exactly
 *    once. Every raw U+005B `[` becomes `[[LIT:U+005B]]`; every unsafe control
 *    code point becomes `[[CTL:U+XXXX]]`; all other code points (including
 *    normal emoji/Indic ZWJ, Persian/Indic ZWNJ, CJK, combining marks and LF)
 *    remain verbatim. This is NOT idempotent and MUST NOT be repeated by a
 *    canonical render/replay stage. The caller-supplied redaction marker is a
 *    declared canonical fixed-point literal, substituted after raw redaction,
 *    never inferred from token text.
 *  - CANONICAL render/replay (`textMode: "canonical"`): `neutralizeControlText`
 *    escapes only real unsafe control bytes that still exist. Encoded visible
 *    tokens are printable ASCII, so canonical text is a fixed point: f(f)=f.
 *
 * A non-identity globally injective pure string function cannot also be
 * idempotent. No single function here claims both properties. Encoding is
 * deterministic and pure: no cache, clock, randomness, I/O, schema field or
 * source guessing. `decodeCanonicalIssueText` documents the inverse mapping
 * from canonical field text back to the post-redaction raw source.
 *
 * ZWJ U+200D and ZWNJ U+200C are normal text and are preserved. ZWSP, LRM/RLM,
 * bidi overrides/isolates, ESC/C0/C1/OSC/APC bytes, DEL and invisible format
 * characters remain unsafe and are never re-admitted to a terminal surface.
 */

export const ISSUE_CONTROL_ESCAPE_PREFIX = "[[CTL:U+";
export const ISSUE_CONTROL_ESCAPE_SUFFIX = "]]";
export const ISSUE_LITERAL_ESCAPE_PREFIX = "[[LIT:U+";
export const ISSUE_LITERAL_ESCAPE_SUFFIX = "]]";
export const ISSUE_LITERAL_OPEN_TOKEN = `${ISSUE_LITERAL_ESCAPE_PREFIX}005B${ISSUE_LITERAL_ESCAPE_SUFFIX}`;

/** Human-readable legacy canonical rule (never contains control bytes). */
export const ISSUE_CONTROL_ESCAPE_RULE =
	"外来控制字节（C0/C1/DEL/ESC/ANSI/OSC/APC/bidi/不可见格式字符）一律转为可见转义 " +
	`${ISSUE_CONTROL_ESCAPE_PREFIX}XXXX${ISSUE_CONTROL_ESCAPE_SUFFIX}（XXXX=大写十六进制码位）；` +
	"LF 保留换行，Tab/CR 同规则转义；普通文字/汉字/组合字/正常 ZWJ/ZWNJ 原样保留；" +
	"确定性且重复处理幂等，规范预览/载荷/摘要使用同一固定点表示。";

/** Human-readable, auditable raw-ingress rule. */
export const ISSUE_RAW_TEXT_RULE =
	"raw text-v1：原始 U+005B 逐字编码为 [[LIT:U+005B]]；原始不安全控制码位逐字编码为 [[CTL:U+XXXX]]；" +
	"其它码位（含 ZWJ/ZWNJ/LF/CJK/组合符号）保留；调用方在调用前明确选择 textMode=raw，编码不重复、不要求幂等；" +
	"[REDACTED] 是脱敏后由调用方显式声明的规范固定点字面量；decodeCanonicalIssueText 可逐字还原脱敏后的原始字段。";

export type IssueTextMode = "raw" | "canonical";

/** Whether a UTF-16 code unit is an unsafe control/format code point. */
export function isUnsafeControlCode(cp: number): boolean {
	if (cp === 0x000a || cp === 0x200c || cp === 0x200d) return false;
	if (cp <= 0x001f) return true;
	if (cp >= 0x007f && cp <= 0x009f) return true;
	if (cp === 0x200b || cp === 0x200e || cp === 0x200f) return true;
	if (cp >= 0x2028 && cp <= 0x202e) return true;
	if (cp >= 0x2060 && cp <= 0x206f) return true;
	return cp === 0x00ad || cp === 0x061c || cp === 0x180e || cp === 0xfeff;
}

export interface ControlTextResult {
	/** Neutralized/encoded text (visible, inert, LF-preserving). */
	text: string;
	/** Number of real unsafe control code points replaced. */
	count: number;
}

function controlToken(cp: number): string {
	return `${ISSUE_CONTROL_ESCAPE_PREFIX}${cp.toString(16).toUpperCase().padStart(4, "0")}${ISSUE_CONTROL_ESCAPE_SUFFIX}`;
}

/** Deterministic, idempotent CANONICAL neutralization. Pure string work only. */
export function neutralizeControlText(text: string): ControlTextResult {
	let out = "";
	let count = 0;
	for (let i = 0; i < text.length; i += 1) {
		const cp = text.charCodeAt(i);
		if (isUnsafeControlCode(cp)) {
			out += controlToken(cp);
			count += 1;
		} else {
			out += text[i];
		}
	}
	return { text: out, count };
}

function encodeRawCore(text: string): ControlTextResult {
	let out = "";
	let count = 0;
	for (let i = 0; i < text.length; i += 1) {
		const cp = text.charCodeAt(i);
		if (isUnsafeControlCode(cp)) {
			out += controlToken(cp);
			count += 1;
		} else if (cp === 0x005b) {
			out += ISSUE_LITERAL_OPEN_TOKEN;
		} else {
			out += text[i];
		}
	}
	return { text: out, count };
}

/**
 * RAW ingress encoding, called exactly once at an explicit boundary.
 * `canonicalLiteral` is an explicit post-redaction fixed-point marker; with no
 * marker the core mapping is injective on the raw string alphabet. This
 * encoder deliberately does NOT claim raw-encoder idempotency.
 */
export function encodeRawIssueText(text: string, canonicalLiteral = ""): ControlTextResult {
	const encoded = encodeRawCore(text);
	if (canonicalLiteral === "") return encoded;
	const encodedLiteral = encodeRawCore(canonicalLiteral).text;
	return { text: encoded.text.replaceAll(encodedLiteral, canonicalLiteral), count: encoded.count };
}

/** Explicit mode bridge for model/command callers. */
export function normalizeIssueText(text: string, mode: IssueTextMode, canonicalLiteral = ""): ControlTextResult {
	return mode === "raw" ? encodeRawIssueText(text, canonicalLiteral) : neutralizeControlText(text);
}

/**
 * Traceability oracle for canonical field text produced by the raw boundary.
 * The result may contain real control bytes: use it only for in-memory source
 * verification, NEVER as preview, status, inbox or terminal output.
 */
export function decodeCanonicalIssueText(text: string): string {
	let out = "";
	let i = 0;
	while (i < text.length) {
		if (text.startsWith(ISSUE_LITERAL_OPEN_TOKEN, i)) {
			out += "[";
			i += ISSUE_LITERAL_OPEN_TOKEN.length;
			continue;
		}
		if (text.startsWith(ISSUE_CONTROL_ESCAPE_PREFIX, i)) {
			const end = text.indexOf(ISSUE_CONTROL_ESCAPE_SUFFIX, i + ISSUE_CONTROL_ESCAPE_PREFIX.length);
			if (end > 0) {
				const hex = text.slice(i + ISSUE_CONTROL_ESCAPE_PREFIX.length, end);
				if (/^[0-9A-F]{4,6}$/.test(hex)) {
					const cp = Number.parseInt(hex, 16);
					if (isUnsafeControlCode(cp) && text.slice(i, end + 2) === controlToken(cp)) {
						out += String.fromCharCode(cp);
						i = end + 2;
						continue;
					}
				}
			}
		}
		out += text[i];
		i += 1;
	}
	return out;
}

/** Convenience wrapper returning just the CANONICAL neutralized text. */
export function escapeUntrustedText(text: string): string {
	return neutralizeControlText(text).text;
}

/** CANONICAL terminal representation of a trusted identity value. The stored
 * identity keeps its exact bytes; only real unsafe controls are escaped here.
 * Brackets, already-visible literal/control tokens and normal Unicode (including
 * ZWJ/ZWNJ) are left verbatim, so this display function is a fixed point.
 * Distinct identities may share a display; compare and look up only their exact
 * stored values. Never apply raw ingress encoding to identity. */
export function escapeIssueIdentity(text: string): string {
	return neutralizeControlText(text).text;
}

export function countUnsafeControls(text: string): number {
	return neutralizeControlText(text).count;
}

export function hasUnsafeControls(text: string): boolean {
	for (let i = 0; i < text.length; i += 1) {
		if (isUnsafeControlCode(text.charCodeAt(i))) return true;
	}
	return false;
}
