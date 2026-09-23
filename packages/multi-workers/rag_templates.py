"""rag_templates.py — canonical text templates for `mw rag init` (design D-201).

Single source of template text: `mw.py` renders and writes these strings, and
the manual (T-22) quotes `mw rag init --print` instead of copying any of this
text, so the CLI output and the docs can be pinned together (parity test).

Pure data + rendering only: no file I/O, no config reads, no interactive
prompts and no stdin reads (design D-206 — the command must succeed with
stdin=DEVNULL).
"""

from __future__ import annotations

# Example values used when the user passes no fields (AC-203 / D-206).
DEFAULT_SERVER = "example"
DEFAULT_MCP_URL = "http://localhost:8100/mcp/"
DEFAULT_TOKEN_ENV = "EXAMPLE_MCP_TOKEN"
DEFAULT_SKILL_DIR = "skills/example"
DEFAULT_SKILL_CLI_ENTRY = "python example_cli.py"

# The transport blocks' "inactive" hints (the unselected block is commented out
# as a whole so yaml.safe_load never sees it).
_MCP_INACTIVE_HINT = (
    "transport is 'skill' — this MCP block is inactive. "
    "To talk over MCP set transport: mcp (or both) and uncomment it."
)
_SKILL_INACTIVE_HINT = (
    "transport is 'mcp' — this CLI block is inactive. "
    "To use the local CLI set transport: skill (or both) and uncomment it."
)


def _commented_block(lines: list[str], hint: str) -> list[str]:
    """Comment out a whole block (prefix every line with '# '), keeping the
    original indentation inside the comment, and lead with a one-line hint."""
    out = [f"    # NOTE: {hint}"]
    for line in lines:
        out.append("# " + line if line.strip() else "#")
    return out


def _servers_header(server: str) -> list[str]:
    return [
        "# RAG server table (rag-servers.yml).",
        "#   machine layer: ~/.agents/rag-servers.yml  (shared by every project)",
        "#   project layer: <project>/.mw/rag-servers.yml  (wins field-by-field)",
        "#",
        "# The two layers merge PER FIELD: a value set in the project layer",
        "# replaces the machine value for that field only; an array (sources) is",
        "# replaced wholesale, never concatenated; `null` deletes the field; and",
        "# `mw rag list` prints the winning layer for every field as",
        "# [machine] / [project].",
        "#",
        "# Nothing below is used until the server name appears in target.yml",
        "# `rag.enabled` (see the target section printed by `mw rag init --print`).",
        "servers:",
        f"  {server}:",
    ]


def _transport_block(transport: str) -> list[str]:
    return [
        "    # transport — how mw talks to this server.",
        "    # values: mcp | skill | both   default: mcp",
        "    #   mcp   = remote MCP server over streamable HTTP",
        "    #   skill = local CLI adapter",
        "    #   both  = try MCP first; only on a CONNECTION-level failure do the",
        "    #           read-only tools fall back to the CLI (rewrite/chat never do).",
        "    # example: transport: both",
        f"    transport: {transport}",
    ]


def _adapter_block() -> list[str]:
    return [
        "    # adapter — protocol adapter id.",
        "    # values: overcode-v1 (the only supported value)   default: overcode-v1",
        "    adapter: overcode-v1",
    ]


def _path_roots_block(active: bool) -> list[str]:
    lines = [
        "    # path_roots_file — JSON map (role -> local root) that `mw rag audit`",
        "    # uses to resolve citations on disk (it fills in local_path / exists).",
        "    # Relative values resolve against the project root.",
        "    # values: path string or null   default: null (citations are then",
        "    #         reported as unverified instead of checked on disk)",
        "    # example: .mw/rag-roots.json (written by `mw rag init`)",
    ]
    if active:
        lines.append("    path_roots_file: .mw/rag-roots.json")
    else:
        lines += [
            "    # INACTIVE (--no-roots): the file was not written, so pointing at",
            "    # it would break every citation. Uncomment after creating it.",
            "    # path_roots_file: .mw/rag-roots.json",
        ]
    return lines


def _sources_block() -> list[str]:
    return [
        "    # sources — which data sources this server can query. The 2nd segment",
        "    # of a citation `server:source:file_path:line` must be one of these.",
        "    # values: list of non-empty strings   default: [] (server default)",
        "    # example: [docs, code]",
        "    sources:",
        "      - docs",
        "      - code",
    ]


def _capabilities_block() -> list[str]:
    return [
        "    # capabilities — what the server can do; each key turns on part of",
        "    # the RAG surface (graph lookups / rag_chat / query rewriting).",
        "    # values: boolean   default: false",
        "    capabilities:",
        "      # graph — citation-graph / related-file lookups",
        "      graph: true",
        "      # chat — natural-language q&a over the sources (rag_chat)",
        "      chat: true",
        "      # rewrite — query rewriting before retrieval",
        "      rewrite: true",
    ]


def _mcp_block(url: str, token_env: str) -> list[str]:
    return [
        "    mcp:",
        "      # url — MCP endpoint (streamable HTTP JSON-RPC).",
        "      # values: non-empty URL   required when transport is mcp or both",
        f"      # example: {url}",
        f"      url: {url}",
        "      # token_env — NAME of the environment variable that holds the",
        "      # token. Write the VARIABLE NAME ONLY, never the token value: mw",
        "      # serve reads the value from its own environment and injects it",
        "      # into spawned workers.",
        "      # values: env var name or null   default: null (no auth header)",
        f"      # example: {token_env}",
        f"      token_env: {token_env}",
        "      # timeout_ms — per-request timeout in milliseconds.",
        "      # values: positive integer   default: 180000 (3 min)",
        "      timeout_ms: 180000",
    ]


def _skill_block(skill_dir: str, skill_cli_entry: str) -> list[str]:
    return [
        "    skill:",
        "      # dir — working directory for the CLI, relative to the project root.",
        "      # values: path string or null   default: null (project root)",
        f"      # example: {skill_dir}",
        f"      dir: {skill_dir}",
        "      # cli_entry — command that runs the local CLI adapter.",
        "      # values: non-empty string   required when transport is skill or both",
        f"      # example: {skill_cli_entry}",
        f"      cli_entry: {skill_cli_entry}",
        "      # timeout_ms — per-invocation timeout in milliseconds.",
        "      # values: positive integer   default: 180000 (3 min)",
        "      timeout_ms: 180000",
    ]


def render_servers_template(
    server: str,
    url: str,
    token_env: str,
    transport: str,
    skill_dir: str,
    skill_cli_entry: str,
    active_roots: bool = True,
) -> str:
    """Full text of a rag-servers.yml layer for one example server.

    The block matching `transport` stays active; the other one is commented
    out as a whole (with a hint). Every field carries an inline comment with
    what it is / values / default / example (AC-204). `active_roots=False`
    (from `mw rag init --no-roots`) comments the path_roots_file field out, so
    an active field always points at a file that really exists."""
    lines = _servers_header(server)
    lines += _transport_block(transport)
    lines += _adapter_block()
    lines += _path_roots_block(active_roots)
    lines += _sources_block()
    lines += _capabilities_block()
    mcp = _mcp_block(url, token_env)
    skill = _skill_block(skill_dir, skill_cli_entry)
    if transport in ("mcp", "both"):
        lines += mcp
    else:
        lines += _commented_block(mcp, _MCP_INACTIVE_HINT)
    if transport in ("skill", "both"):
        lines += skill
    else:
        lines += _commented_block(skill, _SKILL_INACTIVE_HINT)
    return "\n".join(lines) + "\n"


def _target_roles_active(server: str) -> list[str]:
    return [
        "  # roles / phases — per-role and per-phase overrides. Each entry takes",
        "  # server | source | require | rewrite (roles may also set chat_budget /",
        "  # time_budget_s).",
        "  roles:",
        "    coding:",
        "      # server — declared server name (default: default_server)",
        f"      server: {server}",
        "      # source — default source segment of `server:source:file_path:line`",
        "      source: docs",
        "      # require — this role must get RAG: required = role.require OR phase.require",
        "      require: false",
        "      # rewrite — allow query rewriting (needs capabilities.rewrite: true)",
        "      rewrite: false",
        "  # phases — key names are CASE-SENSITIVE and must match the phase value in",
        "  # pm-state.md (design != DESIGN).",
        "  phases:",
        "    design:",
        f"      server: {server}",
        "      source: docs",
        "      require: false",
        "      rewrite: false",
    ]


def render_target_rag_template(
    server: str, enabled: bool, with_default_server: bool
) -> str:
    """Text of the target.yml `rag:` section (with comments).

    Every key is rendered as active YAML with an inline comment (AC-204).
    `enabled: []` is the safe default: the placeholder server stays off until
    the user lists it (D-203); roles/phases merely configure it once enabled.
    A target section is only ever written together with a servers file that
    declares `server`, so the references always resolve."""
    lines = [
        "# RAG section for target.yml (appended by `mw rag init`, hand-edited after).",
        "# Servers are declared in .mw/rag-servers.yml (project) or",
        "# ~/.agents/rag-servers.yml (machine); this section selects and configures them.",
        "rag:",
        "  # enabled — server names active in this project (each must be declared",
        "  # in rag-servers.yml). EMPTY or ABSENT means EVERYTHING IS OFF, not on.",
        "  # example: enabled: [example] turns that server on; [] turns RAG off.",
        f"  enabled: [{server}]" if enabled else "  enabled: []",
        "  # default_server — server used by a role/phase that names none.",
        "  # values: a declared server name, or null   default: null",
    ]
    if with_default_server:
        lines.append(f"  default_server: {server}")
    else:
        lines.append("  default_server: null")
    lines += _target_roles_active(server)
    lines += [
        "  # budgets — hard caps on RAG usage per task.",
        "  # chat_budget — max rag_chat calls per task (default: 2).",
        "  # time_budget_s — max seconds of RAG tool time per task (default: 900).",
        "  budgets:",
        "    chat_budget: 2",
        "    time_budget_s: 900",
    ]
    return "\n".join(lines) + "\n"


# rag-roots.json has no comments in JSON, so the explanation rides on a
# `_README` key (keys starting with `_` are ignored by the loader — same style
# as test/fixtures/rag/rag-roots.json).
ROOTS_TEMPLATE = """{
  "_README": [
    "role -> local root, used by `mw rag audit` to resolve citations on disk",
    "(it fills in local_path / exists). Keys starting with _ are ignored.",
    "A citation `server:source:<role>::<relative path>:<line>` is looked up",
    "under roots[role]; a citation with no <role>:: prefix uses 'engine'.",
    "Values may be relative to the project root, so '.' means this project.",
    "Change 'engine' when your RAG server indexes a DIFFERENT tree, and add a",
    "key per extra role (e.g. 'game': '../game'). A citation naming a role that",
    "is missing here is reported by the audit as missing.",
    "The file must stay one JSON object; delete the keys you do not need."
  ],
  "engine": "."
}
"""
