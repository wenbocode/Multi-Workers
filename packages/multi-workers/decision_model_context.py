"""Model-facing context for a frozen prepared decision."""

from collections.abc import Mapping
from decimal import Decimal
import hashlib
from itertools import combinations
import json
import os
import pathlib
import re

import decision
import decision_material_sources
from autopilot import contract_guard


TERMS = {
    "AC": "Acceptance criterion: a required delivery outcome.",
    "API": "Application programming interface.",
    "ASCII": "American Standard Code for Information Interchange.",
    "BLOCKED": "The action cannot proceed under the current conditions.",
    "CPU": "Central processing unit.",
    "DLL": "Dynamic-link library.",
    "CRLF": "Carriage return and line feed.",
    "CSV": "Comma-separated values.",
    "CLI": "Command-line interface.",
    "DAG": "Directed acyclic graph.",
    "DP": "Decision point: a single decision under the registered rules.",
    "DOM": "Document Object Model.",
    "E2E": "End-to-end verification.",
    "EOF": "End of file.",
    "ERROR": "An operation reported an error.",
    "FAIL": "A check ran and did not meet its expected condition.",
    "FPS": "Frames per second.",
    "GPU": "Graphics processing unit.",
    "HTTP": "Hypertext Transfer Protocol.",
    "HTTPS": "Hypertext Transfer Protocol over TLS.",
    "ID": "Identifier.",
    "JSON": "JavaScript Object Notation, the request and response data format.",
    "JSONL": "JSON Lines, one JSON value per line.",
    "L0": "Level zero: the host-side admission and authority checks.",
    "L1": "Level one: isolated unit verification.",
    "L2": "Level 2 integration verification through actual local entry points.",
    "L3": "Level 3 independent verification of delivery evidence.",
    "LF": "Line feed.",
    "OK": "The recorded operation succeeded.",
    "PASS": "The check met its stated condition.",
    "PID": "Process identifier.",
    "PM": "Project manager: the current decision owner and result consumer.",
    "PIE": "Play In Editor, the Unreal Engine editor play session.",
    "QG": "Quality gate: review of the delivery against its current requirements.",
    "SDD": "Specification-driven development.",
    "SDK": "Software development kit.",
    "SHA256": "SHA-256, a 256-bit cryptographic hash function.",
    "TASKS": "AgenticTask phase for preparing executable task cards.",
    "TLS": "Transport Layer Security.",
    "TS": "TypeScript.",
    "UI": "User interface.",
    "URL": "Uniform Resource Locator.",
    "UNVERIFIED": "No conclusive verification has been recorded.",
    "UTF-8": "Unicode Transformation Format using eight-bit code units.",
    "VC": "Verification criterion: the check and its evidence for a requirement.",
    "VERIFY": "Verification result marker.",
}
DESC_FIELDS = {
    "dp-w-type": ("task_goal", "images_required", "task_deliverables"),
    "dp-pm-steer": ("task_goal", "pm_decision_background"),
    "dp-w-check-task": ("task_goal", "completed", "remaining", "blockers"),
    "dp-QG": ("review_requirements", "review_findings", "uncovered_scope"),
    "dp-gate-approve": ("gate_background", "current_state"),
    "dp-sign-key": ("delivery_goal", "actual_completion", "unfinished_impact"),
    "dp-auto": ("task_goal", "current_state", "tried", "unknowns"),
    "dp-route": ("decision_object", "question"),
}
CONTRACT_ID = decision_material_sources.CONTRACT_ID
DESC_BUDGET_LIMIT = 1000
DESC_SENTENCE_BOUNDARY = re.compile(r"[。！？]+[”’」』）\]}]*|[.!?]+[\"'”’)\]}]*(?=\s|$)")
_QUALIFIED_CRITERION = re.compile(
    rf"(?<![A-Za-z0-9_./\\-])(?P<locator>(?:[A-Za-z]:)?[A-Za-z0-9_./\\-]+)"
    rf"#(?P<id>{decision_material_sources.CRITERION_ID_PATTERN})(?![A-Za-z0-9_-])", re.IGNORECASE | re.ASCII,
)
TERM = re.compile(r"(?<![A-Za-z0-9_-])(?:UTF-8|(?:[A-Z]{2,}[0-9]*|[A-Z][0-9]+[A-Z]+|L[0-3]))(?![A-Za-z0-9_-])")
INSTANCE_ID = re.compile(r"(?:PID[0-9]+|(?:AC|VC|FLOW)[0-9]{3})\Z")
IDENTIFIER_ASSIGNMENT = re.compile(
    r"(?i)(?<![\w-])(?:pid|(?:session|run|task|build|context|world)_id)[ \t]*[:=][ \t]*[A-Za-z0-9_-]+"
)
TRACE_EVENT = re.compile(r"^\[(?:FLOW|END)\](?=\s+\d{4}-\d{2}-\d{2}T)")
REASON_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
REASON_FIELDS = ("finding_ids", "remaining_ids")
REMAINING_BUDGET = re.compile(
    r"(?:(?:remaining(?:\s+(?:budget|allowance|time))?|原剩余|剩余(?:预算|时间)?|原余量)\s*[:：]?\s*"
    r"(?P<before>\d+(?:\.\d+)?)\s*(?P<before_unit>seconds?\b|minutes?\b|秒|分钟)"
    r"|(?<![A-Za-z\d.,+-])(?P<after>\d+(?:\.\d+)?)\s*(?P<after_unit>seconds?\b|minutes?\b|秒|分钟)"
    r"\s+(?:still\s+)?remaining\b)",
    re.I,
)
REVIEW_MEANINGS = {
    "met": "The current criterion was checked and satisfied.",
    "unmet": "The current criterion was checked and failed.",
    "unverified": "The current criterion lacks a conclusive verification result.",
}
_CRITERION_NAMES = {
    "AC": ("acceptance criterion", "acceptance criteria", "验收标准", "验收准则"),
    "VC": ("verification criterion", "verification criteria", "verification contract", "验证标准", "验证合同"),
}


def qg_zero_findings(catalog, context):
    """An explicit empty finding map, or old material with explicit empty partitions."""
    if isinstance(context, Mapping) and "reasons" in context:
        reasons = context["reasons"]
        return isinstance(reasons, Mapping) and not reasons
    if not isinstance(catalog, list):
        return False
    fixes = [item for item in catalog if isinstance(item, Mapping)
             and isinstance(item.get("applies_to"), list) and "fix" in item["applies_to"]]
    return bool(fixes) and all(item.get(field) == [] for item in fixes for field in REASON_FIELDS)


def reviewed_criterion_ids(state: Mapping) -> frozenset[str]:
    return frozenset(
        name for name, item in state.get("references", {}).items()
        if item.get("kind") in {"acceptance-criterion", "verification-criterion"} and "review" in item
    )


def describe_measurement(desc):
    count = decision._estimate_tokens("\n".join(desc))
    return {
        "local_budget": {
            "rule": "desc-local-v1",
            "count": count,
            "limit": DESC_BUDGET_LIMIT,
            "passed": count <= DESC_BUDGET_LIMIT,
        },
        "estimated_tokens": count,
        "exact_count": None,
        "exact_limit_passed": None,
    }


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _strings(value):
    if isinstance(value, Mapping):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, str):
        yield value


def _terms_in_prose(value):
    terms = set()
    for text in _strings(value):
        if text.lstrip().startswith("cmd:"):
            continue
        token = text.strip()
        if decision_material_sources._REFERENCE.fullmatch(token) and (
            not any(char.isspace() for char in token) or pathlib.PureWindowsPath(token).is_absolute() or token.startswith("/")
        ):
            continue
        without_files = re.sub(r"(?<!\w)[A-Za-z0-9_/\\.-]+\.[A-Za-z][A-Za-z0-9_-]*(?::\d+(?:-\d+)?)?", "", text)
        prose = IDENTIFIER_ASSIGNMENT.sub("", without_files)
        terms.update(name for name in TERM.findall(prose) if not INSTANCE_ID.fullmatch(name))
    return terms


def _description(dp, material):
    facts = material.get("background", {}) if dp == "dp-auto" else material
    desc = []
    for field in DESC_FIELDS[dp]:
        text = _description_source(facts, field)
        if text is not None:
            # A local fallback for producers that have not authored a synopsis.
            # Keep only a short excerpt of each selected fact.
            excerpt = " ".join(text.split())
            desc.append(excerpt if len(excerpt) <= 160 else excerpt[:159] + "…")
    return desc


AUTO_COMPARISON_FIELD = "preparation.model_context.auto_comparison"
AUTO_EQUIVALENT_PATHS = "candidate paths must differ in an observation, stop or successor"


def auto_preparation_status(issues):
    if (f"{AUTO_COMPARISON_FIELD}.paths", AUTO_EQUIVALENT_PATHS) in issues:
        return "equivalent"
    if any(field in {AUTO_COMPARISON_FIELD, f"{AUTO_COMPARISON_FIELD}.priority", f"{AUTO_COMPARISON_FIELD}.pairs"}
           for field, _problem in issues):
        return "needs-evidence"
    return None


def auto_issues(context, material):
    field = AUTO_COMPARISON_FIELD
    comparison = context.get("auto_comparison") if isinstance(context, Mapping) else None
    if not isinstance(comparison, Mapping) or set(comparison) != {"priority", "budget", "paths", "pairs"}:
        return [(field, "requires a sourced goal priority, remaining budget, bounded paths, and a decision test for each pair")]
    priority = comparison["priority"]
    background = material.get("background", {})
    if (
        not isinstance(priority, Mapping) or set(priority) != {"rule", "source"}
        or not _text(priority["rule"]) or not _text(priority["source"])
        or priority["source"] not in {"background.task_goal", "background.constraints"}
        or not _text(background.get(priority["source"].split(".", 1)[1]))
    ):
        return [(f"{field}.priority", "requires a priority rule anchored to the submitted goal or constraints")]
    budget = comparison["budget"]
    if (
        not isinstance(budget, Mapping) or set(budget) != {"remaining_seconds", "reserve_seconds"}
        or type(budget["remaining_seconds"]) is not int or type(budget["reserve_seconds"]) is not int
        or not 0 <= budget["reserve_seconds"] < budget["remaining_seconds"] <= 2**31 - 1
    ):
        return [(f"{field}.budget", "requires a positive existing allowance and a smaller nonnegative reserve")]
    limits = []
    for match in REMAINING_BUDGET.finditer(background.get("constraints", "")):
        amount = Decimal(match["before"] or match["after"])
        unit = match["before_unit"] or match["after_unit"]
        limits.append(amount * (60 if unit == "分钟" or unit.lower().startswith("minute") else 1))
    if not limits or budget["remaining_seconds"] > min(limits):
        return [(f"{field}.budget.remaining_seconds", "requires an explicit remaining limit in background.constraints and must not exceed it")]
    path_allowance = budget["remaining_seconds"] - budget["reserve_seconds"]
    options = material.get("handling_options", [])
    ids = {item["id"] for item in options}
    paths = comparison["paths"]
    if not isinstance(paths, Mapping) or set(paths) != ids:
        return [(f"{field}.paths", "requires a bounded path for each current candidate")]
    signatures = set()
    for name, path in paths.items():
        if (
            not isinstance(path, Mapping)
            or set(path) != {"max_seconds", "observation", "stop", "successor", "steps"}
            or type(path["max_seconds"]) is not int or path["max_seconds"] <= 0
            or not all(_text(path[key]) for key in ("observation", "stop", "successor"))
        ):
            return [(f"{field}.paths.{name}", "requires a positive hard limit, observable result, stop and conditional successor")]
        if path["max_seconds"] > path_allowance:
            return [(f"{field}.paths.{name}.max_seconds", "exceeds the remaining allowance after the reserve")]
        if re.search(r"\b(?:indefinitely|unbounded|endlessly|infinite(?:ly)?|forever)\b|无限(?:次|循环|重试)|无上限", path["successor"], re.I):
            return [(f"{field}.paths.{name}.successor", "describes an unbounded successor")]
        steps = path["steps"]
        if not isinstance(steps, list) or not 1 <= len(steps) <= 16:
            return [(f"{field}.paths.{name}.steps", "requires 1–16 ordered, bounded steps")]
        durations = {}
        for step in reversed(steps):
            if (
                not isinstance(step, Mapping) or set(step) != {"id", "max_seconds", "on_success", "on_failure"}
                or not isinstance(step["id"], str) or not REASON_ID.fullmatch(step["id"]) or step["id"] in durations
                or type(step["max_seconds"]) is not int or step["max_seconds"] <= 0
                or any(next_id is not None and (not isinstance(next_id, str) or next_id not in durations)
                       for next_id in (step["on_success"], step["on_failure"]))
            ):
                return [(f"{field}.paths.{name}.steps", "each unique step needs a positive limit and forward-only successors or null to stop")]
            durations[step["id"]] = step["max_seconds"] + max(
                durations.get(step["on_success"], 0), durations.get(step["on_failure"], 0)
            )
        if durations[steps[0]["id"]] > path["max_seconds"] or any(step["max_seconds"] > path["max_seconds"] for step in steps):
            return [(f"{field}.paths.{name}.steps", "a bounded branch exceeds the declared path limit")]
        step_order = {step["id"]: i for i, step in enumerate(steps)}
        graph = tuple((step["max_seconds"], step_order.get(step["on_success"]), step_order.get(step["on_failure"]))
                      for step in steps)
        prose = tuple(" ".join(path[key].casefold().split()) for key in ("observation", "stop", "successor"))
        signatures.add((path["max_seconds"], graph, prose))
    if len(signatures) != len(ids):
        return [(f"{field}.paths", AUTO_EQUIVALENT_PATHS)]
    expected = {frozenset(pair) for pair in combinations(ids, 2)}
    pairs = comparison["pairs"]
    if not isinstance(pairs, list) or len(pairs) != len(expected):
        return [(f"{field}.pairs", "requires exactly one decision test for each unordered candidate pair")]
    for pair in pairs:
        if (
            not isinstance(pair, Mapping) or set(pair) != {"candidates", "criterion", "reversal"}
            or not isinstance(pair["candidates"], list) or len(pair["candidates"]) != 2
            or not all(_text(item) for item in pair["candidates"])
            or not _text(pair["criterion"]) or not _text(pair["reversal"])
        ):
            return [(f"{field}.pairs", "each pair needs two candidates, a comparison rule and reversal evidence")]
        names = frozenset(pair["candidates"])
        if names not in expected:
            return [(f"{field}.pairs", "contains an unknown or repeated candidate pair")]
        expected.remove(names)
    return []


def _references(required, mentioned, review, root, key):
    if not required and not mentioned:
        return {}, []
    if not root or not key or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", key) or key.endswith("."):
        if not required:
            return {}, []
        raise decision_material_sources.SourceMaterialError(
            (("model_context.references", "criterion text requires the current bound key"),)
        )
    root = pathlib.Path(root).resolve()
    key_dir = root / ".agenticdoc" / key
    definitions = {}
    malformed = {}
    malformed_details = {}
    replacements = {}
    dependencies = []
    for filename, parse in (("spec.md", contract_guard.parse_acs), ("design.md", contract_guard.parse_vcs)):
        path = key_dir / filename
        try:
            canonical = path.resolve(strict=True)
            if not canonical.is_relative_to(key_dir) or not canonical.is_file():
                raise OSError("outside key")
            with canonical.open("rb") as handle:
                content = handle.read(decision_material_sources.MAX_SOURCE_BYTES + 1)
            if len(content) > decision_material_sources.MAX_SOURCE_BYTES:
                raise OSError("document too large")
            text = content.decode("utf-8-sig")
            if filename == "design.md":
                definitions.update(parse(text, malformed=malformed, malformed_details=malformed_details))
            else:
                definitions.update(parse(text))
                replacements = _scope_replacements(text)
            dependencies.append({
                "path": str(path), "canonical_path": str(canonical),
                "sha256": hashlib.sha256(content).hexdigest(),
            })
        except (OSError, RuntimeError, UnicodeError):
            continue
    pending = sorted(required | (mentioned & definitions.keys() if not review else set()))
    historical = (mentioned - required) & (replacements.keys() - definitions.keys())
    if not pending and not historical:
        return {}, dependencies
    freeze_path = contract_guard.freeze_path(key_dir)
    frozen = None
    try:
        try:
            freeze_path.lstat()
        except FileNotFoundError:
            dependencies.append({"path": str(freeze_path), "canonical_path": None, "sha256": None, "status": "missing"})
        else:
            canonical = freeze_path.resolve(strict=True)
            if not canonical.is_relative_to(key_dir) or not canonical.is_file():
                raise ValueError("invalid freeze path")
            with canonical.open("rb") as handle:
                raw = handle.read(decision_material_sources.MAX_SOURCE_BYTES + 1)
            if len(raw) > decision_material_sources.MAX_SOURCE_BYTES:
                raise ValueError("oversized freeze")
            frozen = json.loads(raw)
            if (not isinstance(frozen, Mapping) or frozen.get("schema") != contract_guard.FREEZE_SCHEMA
                    or frozen.get("key") != key or any(not isinstance(frozen.get(name), Mapping) for name in ("spec", "design"))):
                raise ValueError("invalid freeze contents")
            dependencies.append({"path": str(freeze_path), "canonical_path": str(canonical), "sha256": hashlib.sha256(raw).hexdigest()})
    except (OSError, RuntimeError, ValueError) as exc:
        raise decision_material_sources.SourceMaterialError((("model_context.references", "the bound contract freeze is unreadable"),)) from exc
    result = {}
    while pending:
        name = pending.pop(0)
        if name in result:
            continue
        body = definitions.get(name)
        if not body:
            diagnostics = None
            detail = "missing current criterion text in the bound spec or design"
            if name in malformed:
                detail = malformed_details[name]
                diagnostics = [{"field": f"model_context.references.{name}", "code": "criterion-reference-unresolved",
                                "path": f".agenticdoc/{key}/design.md",
                                "source_line": malformed[name]}]
            raise decision_material_sources.SourceMaterialError(
                ((f"model_context.references.{name}", detail),), dependencies, diagnostics,
            )
        family = "spec" if name.startswith("AC-") else "design"
        if frozen is not None and frozen[family].get(name) != contract_guard.canonical_sha(name, body):
            raise decision_material_sources.SourceMaterialError(
                ((f"model_context.references.{name}", "criterion text differs from the bound contract freeze"),),
                dependencies,
            )
        if name.startswith("AC-"):
            entry = {"kind": "acceptance-criterion", "text": body}
        else:
            assertion, layer, output, source = body.split("\x1f")
            ac_ids = sorted({name.upper() for name in CONTRACT_ID.findall(source)})
            entry = {"kind": "verification-criterion", "text": assertion, "layer": layer,
                     "expected_output": output, "source_criteria": ac_ids}
            pending.extend(ac_ids)
        if name in review:
            entry["review"] = review[name]
        result[name] = entry
    for name in sorted(historical):
        targets, line = replacements[name]
        if all(target in definitions and (frozen is None or
               frozen["spec" if target.startswith("AC-") else "design"].get(target)
               == contract_guard.canonical_sha(target, definitions[target])) for target in targets):
            result[name] = {"kind": "historical-criterion", "superseded_by": targets,
                            "source": f".agenticdoc/{key}/spec.md:{line}"}
    return result, dependencies


def _scope_replacements(spec):
    """Read the explicit old-to-current scope table from the bound spec."""
    replacements = {}
    in_table = False
    for line, text in enumerate(spec.splitlines(), 1):
        cells = text.strip().strip("|").split("|")
        if len(cells) != 3 or not text.lstrip().startswith("|"):
            in_table = False
            continue
        old, current, _ = (cell.strip() for cell in cells)
        if (old, current) == ("历史判据", "现行判据") or (
            re.fullmatch(r"v\d+要求", old) and re.fullmatch(r"v\d+去向", current)
        ):
            in_table = True
            continue
        if not in_table or not cells[2].strip():
            continue
        if not re.fullmatch(r"(?:AC|VC)-\d{3}(?:[、, ]+(?:(?:AC|VC)-)?\d{3})*", current, re.I):
            continue
        if match := re.fullmatch(r"v\d+\s+(\d{3})\s*/\s*原VC-(\d{3})(?:[–-](\d{3}))?", old):
            first, last = int(match[2]), int(match[3] or match[2])
            if last < first:
                continue
            names = [f"AC-{match[1]}", *(f"VC-{number:03}" for number in range(first, last + 1))]
        elif match := re.fullmatch(rf"(?:旧|原|previous\s+)?(?P<id>{decision_material_sources.CRITERION_ID_PATTERN})", old, re.I):
            names = [match["id"].upper()]
        else:
            continue
        family = current[:2].upper()
        targets = []
        for name in re.split(r"[、, ]+", current.upper()):
            if CONTRACT_ID.fullmatch(name):
                family = name[:2]
            targets.append(f"{family}-{name[-3:]}")
        for name in names:
            if name in replacements:
                replacements[name] = None
            else:
                replacements[name] = (targets, line)
    return {name: row for name, row in replacements.items() if row is not None}


def project(dp, material, preparation, questions, options):
    """Project the authored model fields before hydrating source evidence."""
    context = preparation.get("model_context", {})
    field = "preparation.model_context"
    issues = []
    if not isinstance(context, Mapping) or set(context) - {
        "desc", "terminology", "review", "reasons", "auto_comparison", "references", "enum_meanings",
    }:
        raise decision_material_sources.SourceMaterialError(((field, "unknown model context fields"),))
    desc = context.get("desc", _description(dp, material))
    if not isinstance(desc, list) or not 1 <= len(desc) <= 10 or not all(_text(line) for line in desc):
        issues.append((f"{field}.desc", "supply 1–10 nonempty sentences"))
    else:
        sentences = sum(max(1, sum(bool(part.strip()) for part in DESC_SENTENCE_BOUNDARY.split(line))) for line in desc)
        if sentences > 10:
            issues.append((f"{field}.desc", f"{sentences} sentences exceed the limit of 10"))
        budget = describe_measurement(desc)["local_budget"]
        if not budget["passed"]:
            issues.append((f"{field}.desc", f"{budget['rule']} count {budget['count']} exceeds the limit of {budget['limit']}"))
    terminology = context.get("terminology", {})
    if not isinstance(terminology, Mapping) or any(not _text(key) or not _text(value) for key, value in terminology.items()):
        issues.append((f"{field}.terminology", "expected a map from term to its nonempty definition"))
    review = context.get("review", {})
    if not isinstance(review, Mapping) or any(
        not isinstance(name, str) or name != name.upper() or not CONTRACT_ID.fullmatch(name) or not isinstance(item, Mapping)
        or set(item) != {"status", "evidence"}
        or item["status"] not in ("met", "unmet", "unverified") or not _text(item["evidence"])
        for name, item in review.items()
    ) or (review and dp not in ("dp-QG", "dp-sign-key")):
        issues.append((f"{field}.review", "supply current AC/VC status and evidence for a quality or sign request"))
    reasons = context.get("reasons", {})
    if not isinstance(reasons, Mapping) or any(
        not isinstance(name, str) or not REASON_ID.fullmatch(name) or not _text(body) for name, body in reasons.items()
    ):
        issues.append((f"{field}.reasons", "expected a map from stable reason id to its nonempty definition"))
    enums = context.get("enum_meanings", {})
    if not isinstance(enums, Mapping) or len(enums) > 64 or any(
        not isinstance(name, str) or not REASON_ID.fullmatch(name) or not _text(body) for name, body in enums.items()
    ):
        issues.append((f"{field}.enum_meanings", "expected at most 64 code definitions with nonempty meaning"))
    declared_refs = context.get("references", {})
    generic = {}
    context_refs = []
    if not isinstance(declared_refs, Mapping) or len(declared_refs) > 64:
        issues.append((f"{field}.references", "expected a map of at most 64 named references"))
    else:
        for name, entry in declared_refs.items():
            if (
                not isinstance(name, str) or not REASON_ID.fullmatch(name) or CONTRACT_ID.fullmatch(name)
                or not isinstance(entry, Mapping) or not _text(entry.get("kind"))
            ):
                issues.append((f"{field}.references", "expected stable non-criterion ids with a reference kind"))
                continue
            kind = entry["kind"].strip().casefold().replace("_", "-").replace(" ", "-")
            if kind in {"acceptance-criterion", "verification-criterion", "verification-contract", "historical-criterion"}:
                issues.append((f"{field}.references.{name}", "cite criterion ids from the bound contract without redefining them"))
                continue
            if entry.keys() == {"kind", "text"} and _text(entry["text"]):
                if isinstance(reasons, Mapping) and name in reasons and entry["text"].strip() != str(reasons[name]).strip():
                    issues.append((f"{field}.references.{name}", "conflicts with the prepared reason definition"))
                generic[name] = dict(entry)
            elif entry.keys() in ({"kind", "path"}, {"kind", "path", "lines"}) and _text(entry["path"]):
                generic[name] = {"kind": entry["kind"]}
                context_refs.append({"field": f"{field}.references.{name}.path", **{
                    attr: entry[attr] for attr in ("path", "lines") if attr in entry
                }})
            else:
                issues.append((f"{field}.references.{name}", "expected inline text or a file and optional line range"))
    if dp == "dp-auto":
        issues.extend(auto_issues(context, material))
    elif "auto_comparison" in context:
        issues.append((f"{field}.auto_comparison", "only dp-auto accepts path comparison"))
    if issues:
        raise decision_material_sources.SourceMaterialError(tuple(issues))
    catalog = preparation["basis_catalog"]
    if dp == "dp-QG" and (context or any(field in basis for basis in catalog for field in REASON_FIELDS)):
        zero = qg_zero_findings(catalog, context)
        for index, basis in enumerate(catalog):
            if "fix" not in basis["applies_to"]:
                continue
            selected = set(basis.get("finding_ids", []))
            path = f"preparation.basis_catalog[{index}]"
            if (not zero and not selected) or selected - reasons.keys():
                issues.append((f"{path}.finding_ids", "select only current finding ids from model_context.reasons"))
            elif "remaining_ids" in basis and set(basis["remaining_ids"]) != reasons.keys() - selected:
                issues.append((f"{path}.remaining_ids", "omit remaining_ids or match the findings not selected for this fix"))
        if issues:
            raise decision_material_sources.SourceMaterialError(tuple(issues))
    selected_reason_ids = {
        reason_id for basis in catalog
        for name in REASON_FIELDS for reason_id in basis.get(name, [])
    }
    missing = selected_reason_ids - reasons.keys()
    if missing:
        raise decision_material_sources.SourceMaterialError(tuple(
            (f"{field}.reasons.{name}", "missing definition of prepared reason id") for name in sorted(missing)
        ))
    if dp == "dp-QG" and reasons:
        selected_reason_ids.update(reasons)
    model_fields = {"desc": desc}
    if selected_reason_ids:
        model_fields["reasons"] = {name: reasons[name] for name in sorted(selected_reason_ids)}
    if dp == "dp-auto":
        model_fields["path_comparison"] = context["auto_comparison"]
    model_fields["references"] = generic
    choice_meanings = {}
    for option in options.values():
        choice = option["choice"]
        label = option["choice_label"]
        if label == choice and dp == "dp-route":
            point = decision._protocol_module().get_decision_point(choice)
            label = point.description if point is not None else label
        choice_meanings[choice] = label
    status_meanings = {item["status"]: REVIEW_MEANINGS[item["status"]] for item in review.values()}
    model_fields["enum_meanings"] = enums | choice_meanings | status_meanings
    observed = _terms_in_prose([material, questions, model_fields, review])
    defined = TERMS | terminology
    leaves = decision_material_sources._string_leaves
    authored = {}
    basis_text = [(f"preparation.basis_catalog[{index}].text", item["text"])
                  for index, item in enumerate(preparation["basis_catalog"])]
    for source_field, text in leaves(material) + basis_text + leaves({
        name: context[name] for name in ("desc", "review", "reasons", "auto_comparison", "enum_meanings") if name in context
    } | {"references": generic}, field):
        for name in _terms_in_prose(text) - defined.keys():
            authored.setdefault(name, source_field)
    model_fields["terminology"] = {name: defined[name] for name in sorted((observed & defined.keys()) | terminology.keys())}
    return model_fields, context_refs, authored


def field_trace(dp, material, preparation, state, options, *, key=None, instruction_source=None):
    """Local pointers into the submitted book, registry and actual source excerpts."""
    context = preparation.get("model_context", {})
    base = "/preparation/model_context"
    trace = {}

    def put(destination, *sources, transform="copy"):
        trace[destination] = {"sources": list(sources), "transform": transform}

    def escape(component):
        return str(component).replace("~", "~0").replace("/", "~1")

    def copy_fields(value, path):
        if isinstance(value, Mapping) and value:
            for name, child in value.items():
                copy_fields(child, f"{path}/{escape(name)}")
        elif isinstance(value, list) and value:
            for index, child in enumerate(value):
                copy_fields(child, f"{path}/{index}")
        else:
            put(f"/state{path}", f"book:{path}")

    copy_fields(material, "/material")
    if "desc" in context:
        for index in range(len(state["desc"])):
            put(f"/state/desc/{index}", f"book:{base}/desc/{index}")
    else:
        path = "/material/background" if dp == "dp-auto" else "/material"
        facts = material["background"] if dp == "dp-auto" else material
        for index, name in enumerate(name for name in DESC_FIELDS[dp] if _description_source(facts, name) is not None):
            put(f"/state/desc/{index}", f"book:{path}/{name}", transform="short-description")
    for name in state["terminology"]:
        path_name = escape(name)
        uses_criterion = name in _CRITERION_NAMES and any(ref.startswith(name + "-") for ref in state["references"])
        if name in context.get("terminology", {}) and not uses_criterion:
            put(f"/state/terminology/{path_name}", f"book:{base}/terminology/{path_name}")
        else:
            put(f"/state/terminology/{path_name}", f"registry:terminology/{path_name}")
    if not state["terminology"]:
        put("/state/terminology", "registry:terminology", transform="no-cited-terms")
    choices = {item["choice"]: item for item in options.values()}
    for name in state["enum_meanings"]:
        if name in REVIEW_MEANINGS and any(row["status"] == name for row in context.get("review", {}).values()):
            put(f"/state/enum_meanings/{name}", f"registry:review/{name}")
        elif name in choices:
            option = choices[name]
            source = option["choice_label_source"]
            if dp == "dp-route" and option["choice_label"] == name:
                source = f"registry:{name}/description"
            put(f"/state/enum_meanings/{name}", source, transform="active-choice-label")
        else:
            put(f"/state/enum_meanings/{name}", f"book:{base}/enum_meanings/{name}")
    for name, value in state["references"].items():
        target = f"/state/references/{name}"
        if value["kind"] == "historical-criterion":
            put(target, f"contract:{value['source']}", transform="historical-scope")
        elif CONTRACT_ID.fullmatch(name):
            doc = "spec.md" if name.startswith("AC") else "design.md"
            put(target, f"contract:{key}/{doc}#{name}", transform="current-criterion")
            if "review" in value:
                put(f"{target}/review", f"book:{base}/review/{name}")
        elif "source_id" in value:
            put(target, f"book:{base}/references/{name}", f"source:{value['source_id']}", transform="file-reference")
        else:
            put(target, f"book:{base}/references/{name}")
    if not state["references"]:
        put("/state/references", f"book:{base}/references", transform="no-cited-references")
    for name in state.get("reasons", {}):
        put(f"/state/reasons/{name}", f"book:{base}/reasons/{name}")
    if "path_comparison" in state:
        put("/state/path_comparison", f"book:{base}/auto_comparison", transform="validated-comparison")
    for index, entry in enumerate(state.get("evidence_sources", [])):
        put(f"/state/evidence_sources/{index}", f"source:{entry['source_id']}", *entry["references"],
            transform=entry["representation"])
    basis_indices = {item["id"]: index for index, item in enumerate(preparation["basis_catalog"])}
    for wire, option in options.items():
        index = basis_indices[option["basis_id"]]
        put(f"/questions/decision_selection/criteria/{wire}", f"book:/preparation/basis_catalog/{index}",
            option["choice_label_source"], transform="legal-pair")
    put("/questions/decision_selection/instructions", instruction_source or f"registry:{dp}/instructions",
        "registry:prepared_basis_instructions", transform="prepared-single-choice")
    put("/questions/decision_selection/type", f"registry:{dp}/protocol", transform="prepared-single-choice")
    put("/model", "transport:resolved_model", transform="resolve-config")
    return {"fields": trace, "local_only": ["/meta", "/notes", "/preparation/prepared_at", "/preparation/basis_catalog"]}


def resolve_criterion_references(state, questions, preparation, *, root, key):
    """Bind explicit criterion references and retain ordinary mentions as context."""
    review = preparation.get("model_context", {}).get("review", {})
    doc_root = pathlib.Path(root).resolve() / ".agenticdoc" if root else None
    key_dir = doc_root / key if doc_root is not None and key else None
    mentions = {name: f"preparation.model_context.review.{name}" for name in review}
    required = set(review)

    def outside_current_key(path):
        try:
            lexical = pathlib.Path(os.path.abspath(path))
            return key_dir is None or not lexical.is_relative_to(key_dir) or not lexical.resolve().is_relative_to(key_dir)
        except (OSError, RuntimeError, ValueError):
            return True

    def check(text, field, source_path=None, *, explicit_links=True):
        ids = [name.upper() for name in CONTRACT_ID.findall(text)]
        if not ids:
            return
        foreign = (source_path is not None and any(part.casefold() == ".agenticdoc" for part in source_path.parts)
                   and outside_current_key(source_path))
        for match in _QUALIFIED_CRITERION.finditer(text) if explicit_links else ():
            locator = pathlib.PurePosixPath(match["locator"].replace("\\", "/")).as_posix()
            name = match["id"].upper()
            target = pathlib.Path(locator)
            if root and not target.is_absolute():
                base = source_path.parent if source_path is not None and not locator.startswith(".agenticdoc/") else pathlib.Path(root)
                target = base / target
            filename = "spec.md" if name.startswith("AC-") else "design.md"
            local = locator in {key, filename} or (
                pathlib.Path(os.path.abspath(target)) == key_dir / filename and not outside_current_key(target)
                if key_dir is not None else False
            )
            if local and not foreign:
                required.add(name)
                continue
            raise decision_material_sources.SourceMaterialError(
                ((field, f"{name} must cite the current key's {filename}"),), state.file_evidence,
                [{"field": field, "code": "criterion-reference-other-object", "criterion": name}],
            )
        if not foreign:
            for name in ids:
                mentions.setdefault(name, field)

    leaves = decision_material_sources._string_leaves
    for field, text in (leaves(state["material"]) + leaves({
        name: value for name, value in state.items() if name not in {"material", "evidence_sources", "quality_gate"}
    }, "state") + leaves(questions, "questions")):
        check(text, field)
    for field, text in leaves(review, "preparation.model_context.review"):
        check(text, field)
    for index, source in enumerate(state.get("evidence_sources", [])):
        path = pathlib.Path(source["path"])
        review_fields = [field for field in source["references"] if field.startswith("preparation.model_context.review.")]
        if review_fields and any(
                part.casefold() == ".agenticdoc" for part in path.parts
            ) and outside_current_key(path):
            raise decision_material_sources.SourceMaterialError(
                ((review_fields[0], "current review evidence is outside the bound key"),), state.file_evidence,
                [{"field": review_fields[0], "code": "criterion-reference-other-object"}],
            )
        check(source["text"], f"state.evidence_sources[{index}].text", path,
              explicit_links=bool(review_fields) or path.suffix.lower() != ".log")

    try:
        references, dependencies = _references(required, set(mentions), review, root, key)
    except decision_material_sources.SourceMaterialError as exc:
        diagnostics = []
        for item in exc.diagnostics:
            name = item["field"].rsplit(".", 1)[-1]
            diagnostic = {**item, "code": "criterion-reference-unresolved"}
            if name in mentions:
                diagnostic.update(criterion=name, source_field=mentions[name])
            diagnostics.append(diagnostic)
        raise decision_material_sources.SourceMaterialError(exc.issues, state.file_evidence + exc.file_evidence, diagnostics) from exc
    existing = {os.path.normcase(item.get("canonical_path") or item["path"]): item for item in state.file_evidence}
    for dependency in dependencies:
        prior = existing.get(os.path.normcase(dependency.get("canonical_path") or dependency["path"]))
        if prior is None:
            state.file_evidence.append(dependency)
        elif prior.get("sha256") != dependency["sha256"]:
            raise decision_material_sources.SourceMaterialError(
                (("model_context.references", "the contract changed during source hydration"),), state.file_evidence,
            )
    state["references"].update(references)
    authored = preparation.get("model_context", {}).get("terminology", {})
    for term in {name.split("-", 1)[0] for name in references}:
        if term in authored and not authored[term].strip().casefold().startswith(_CRITERION_NAMES[term]):
            raise decision_material_sources.SourceMaterialError(
                ((f"preparation.model_context.terminology.{term}", "definition conflicts with the bound contract terminology"),),
                state.file_evidence,
            )
        state["terminology"][term] = TERMS[term]


def terminology_issues(state, authored, project_root):
    """Collect definitions needed by the authored text and the retained evidence."""
    evidence = state.get("evidence_sources", [])
    references = state["references"]
    named_sources = {entry["source_id"] for entry in references.values() if "source_id" in entry}
    definition_fields = {}
    for name, entry in references.items():
        for term in _terms_in_prose(entry.get("text")):
            definition_fields.setdefault(term, f"state.references.{name}")
    terms = set(definition_fields)
    sources_by_term = {}
    for row in evidence:
        source_path = pathlib.Path(row["path"])
        suffix = source_path.suffix.lower()
        if suffix not in {".txt", ".md", ".rst", ".log"} and row["source_id"] not in named_sources:
            continue
        line_numbers = (line for start, end in row["included_lines"] for line in range(start, end + 1))
        for number, text in zip(line_numbers, row["text"].splitlines()):
            if row["representation"] == "excerpt":
                text = text.partition(": ")[2]
            if suffix == ".log":
                text = TRACE_EVENT.sub("", text)
            for term in _terms_in_prose(text):
                terms.add(term)
                sources_by_term.setdefault(term, (row, number))
    glossary = state["terminology"]
    for name in sorted((terms & TERMS.keys()) - glossary.keys()):
        glossary[name] = TERMS[name]
    issues = []
    diagnostics = []
    root = pathlib.Path(project_root).resolve() if project_root is not None else None
    for name in sorted((terms | authored.keys()) - glossary.keys()):
        field = f"preparation.model_context.terminology.{name}"
        origin = "submitted decision material" if name in authored else "referenced prose"
        issues.append((field, f"missing definition of a term in {origin}"))
        item = {"field": field, "code": "undefined-term"}
        if name in authored:
            item["source_field"] = authored[name]
        elif name in definition_fields:
            item["source_field"] = definition_fields[name]
        if root is not None and name in sources_by_term:
            row, line = sources_by_term[name]
            path = decision_material_sources._display_path(pathlib.Path(row["path"]), root)
            if path is not None:
                item["path"] = path
                item["source_line"] = line
            if len(row["included_lines"]) == 1:
                start, end = row["included_lines"][0]
                item["requested_lines"] = {"start": start, "end": end}
                item["file_line_count"] = row["source_lines"]
        diagnostics.append(item)
    return issues, diagnostics


def _description_source(facts, name):
    """The exact fact the fallback summary selected for one sentence."""
    if name == "images_required" and isinstance(facts.get(name), bool):
        return "Images are required" if facts[name] else "No images are required"
    return next(_strings(facts.get(name)), None)
