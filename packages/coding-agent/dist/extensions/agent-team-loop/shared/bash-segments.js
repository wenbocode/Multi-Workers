/**
 * Quote-aware bash segment lexer (mw-worktree-junction-guard W-01, D-3).
 *
 * Extracted verbatim from implementation-gate.ts so the target-side write
 * gate and the worktree/junction guard share ONE lexer instead of keeping
 * two drifting copies (the IN-3 class of incident: a second copy that
 * diverges from the original). The accident command
 * `git worktree remove --force "$env:TEMP\qg-head"` has a non-literal
 * target: the resolution layer must first be able to lift that token out
 * unchanged (quotes stripped, interpolation NOT expanded), which is exactly
 * what this lexer does.
 *
 * Split a command into `;`/`&&`/`||`/`|`/`&`/paren-separated segments with
 * quote-aware, escape-aware words and redirect targets captured separately
 * from payload words. Heredoc bodies are skipped as payload text.
 */
/** Read the heredoc delimiter right after `<<` (optional `-`, optional
 * quotes). Returns the delimiter and the scan position after it. */
function readHeredocDelimiter(command, start) {
    let i = start;
    const n = command.length;
    if (command[i] === "-")
        i += 1; // <<- form
    while (command[i] === " " || command[i] === "\t")
        i += 1;
    let delim = "";
    if (command[i] === "'" || command[i] === '"') {
        const quote = command[i];
        i += 1;
        while (i < n && command[i] !== quote) {
            delim += command[i];
            i += 1;
        }
        if (i < n)
            i += 1;
    }
    else {
        while (i < n && !/[\s;&|<>()]/.test(command[i] ?? "")) {
            delim += command[i];
            i += 1;
        }
    }
    return { delim, next: i };
}
/** From the newline ending the heredoc operator line, skip body lines until
 * the delimiter line; returns the position at the terminator after it
 * (or EOF). A line with extra text after the delimiter does not terminate
 * the heredoc — the rest of the command is then skipped too, which can only
 * under-block, never false-positive. */
function skipHeredocBody(command, start, delim) {
    let i = start;
    const n = command.length;
    while (i < n) {
        i += 1; // consume the line terminator
        let line = "";
        while (i < n && command[i] !== "\n") {
            line += command[i];
            i += 1;
        }
        if (line.trim() === delim)
            return i;
    }
    return i;
}
/** Characters a backslash actually escapes outside quotes: the POSIX shell
 * metacharacters that carry lexical structure here. Before any other
 * character the backslash stays literal — required for Windows path
 * separators (`H:\repo\packages\x.py` must not collapse to `H:repopackagesx.py`)
 * and matching POSIX shells, where `echo a\b` prints `a\b`. */
const BACKSLASH_ESCAPES_UNQUOTED = new Set([
    " ",
    "\t",
    "\r",
    "\n",
    ";",
    "&",
    "|",
    "<",
    ">",
    "(",
    ")",
    "'",
    '"',
    "\\",
    "$",
    "`",
]);
/** Inside double quotes a backslash only escapes $ ` " \\ and newline (POSIX);
 * everywhere else — including the separators of a Windows path — it is a
 * literal character. */
const BACKSLASH_ESCAPES_DOUBLE_QUOTED = new Set(["$", "`", '"', "\\", "\n"]);
/** Split a command into `;`/`&&`/`||`/`|`/`&`/paren-separated segments with
 * quote-aware, escape-aware words and redirect targets captured separately
 * from payload words. Quote content is always literal (a quoted `>` is
 * text, not a redirect — the false-positive lesson from P-002's bash
 * heuristic). Heredoc bodies are skipped entirely: they are payload text,
 * and scanning them would let a doc that quotes shell commands fire the
 * gate. */
export function parseBashSegments(command) {
    const segments = [];
    let current = { words: [], redirectTargets: [] };
    let word = "";
    let hasWord = false;
    let quote = null;
    let pendingRedirect = false;
    let pendingRead = false;
    let heredocDelim;
    const flushWord = () => {
        if (!hasWord)
            return;
        if (pendingRedirect) {
            current.redirectTargets.push(word);
        }
        else if (!pendingRead) {
            current.words.push(word);
        }
        pendingRedirect = false;
        pendingRead = false;
        word = "";
        hasWord = false;
    };
    const endSegment = () => {
        flushWord();
        pendingRedirect = false;
        pendingRead = false;
        if (current.words.length > 0 || current.redirectTargets.length > 0)
            segments.push(current);
        current = { words: [], redirectTargets: [] };
    };
    let i = 0;
    const n = command.length;
    while (i < n) {
        const c = command[i] ?? "";
        if (quote !== null) {
            if (c === "\\" && quote === '"') {
                const next = command[i + 1];
                if (next !== undefined && BACKSLASH_ESCAPES_DOUBLE_QUOTED.has(next)) {
                    word += next;
                    hasWord = true;
                    i += 2;
                }
                else {
                    // literal backslash (Windows path separator before an ordinary char)
                    word += c;
                    hasWord = true;
                    i += 1;
                }
                continue;
            }
            if (c === quote) {
                quote = null;
                i += 1;
                continue;
            }
            word += c;
            hasWord = true;
            i += 1;
            continue;
        }
        if (c === "'" || c === '"') {
            quote = c;
            hasWord = true;
            i += 1;
            continue;
        }
        if (c === "\\") {
            const next = command[i + 1];
            if (next !== undefined && BACKSLASH_ESCAPES_UNQUOTED.has(next)) {
                word += next;
                hasWord = true;
                i += 2;
            }
            else {
                // literal backslash (Windows path separator before an ordinary char)
                word += c;
                hasWord = true;
                i += 1;
            }
            continue;
        }
        if (c === " " || c === "\t" || c === "\r") {
            flushWord();
            i += 1;
            continue;
        }
        if (c === "\n") {
            flushWord();
            if (heredocDelim !== undefined) {
                i = skipHeredocBody(command, i, heredocDelim);
                heredocDelim = undefined;
                continue;
            }
            i += 1;
            continue;
        }
        if (c === ";") {
            endSegment();
            i += 1;
            continue;
        }
        if (c === "&") {
            if (command[i + 1] === "&") {
                endSegment();
                i += 2;
                continue;
            }
            if (command[i + 1] === ">") {
                flushWord(); // &> redirects both streams
                pendingRedirect = true;
                i += 2;
                continue;
            }
            endSegment();
            i += 1;
            continue;
        }
        if (c === "|") {
            endSegment();
            i += command[i + 1] === "|" ? 2 : 1;
            continue;
        }
        if (c === "(" || c === ")") {
            endSegment();
            i += 1;
            continue;
        }
        if (c === "<") {
            if (command[i + 1] === "<") {
                flushWord();
                const parsed = readHeredocDelimiter(command, i + 2);
                heredocDelim = parsed.delim === "" ? undefined : parsed.delim;
                i = parsed.next;
                continue;
            }
            flushWord();
            pendingRead = true; // input redirect: the next word is a read side, dropped
            i += 1;
            continue;
        }
        if (c === ">") {
            if (hasWord && /^\d+$/.test(word)) {
                // fd-prefixed form (2>log): the digits are the fd number, not a word
                word = "";
                hasWord = false;
            }
            else {
                flushWord();
            }
            pendingRedirect = true;
            i += command[i + 1] === ">" ? 2 : 1;
            continue;
        }
        word += c;
        hasWord = true;
        i += 1;
    }
    flushWord();
    if (current.words.length > 0 || current.redirectTargets.length > 0)
        segments.push(current);
    return segments;
}
//# sourceMappingURL=bash-segments.js.map