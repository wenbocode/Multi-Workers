"""Read a module-local package with progressively disclosed context."""
import argparse
import csv
import difflib
import hashlib
import json
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import module_config


ROOT = Path(__file__).resolve().parents[1]
FIELDS = {
    "terms": "term_id,term,alias,definition,unit,owner,path,symbol,ast_id",
    "testcases": "case_id,term_id,name,path,preconditions,steps,expected,command,status,decision_ref",
    "gates": "gate_id,term_id,requirement,case_id,selection,trigger,runner,args,artifacts,status,decision_ref",
    "records": "record_id,term_id,case_id,kind,time,source_revision,path,summary",
}
TERM_REF = re.compile(r"\[(T-[A-Z0-9-]+)\]")
NODE_REF = re.compile(r"\[N:([A-Za-z_~][A-Za-z0-9_:~]*)\]")


class PackageError(ValueError):
    pass


def local_path(root, value):
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise PackageError("Path escapes module: " + value)
    return path


def fingerprint(root, paths):
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def item_digest(rows, root=None):
    """Bind an individual approval to all of its semantic association rows."""
    content = [{key: value for key, value in row.items() if key not in ("status", "decision_ref")} for row in rows]
    serialized = sorted(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in content)
    digest = hashlib.sha256("\n".join(serialized).encode("utf-8"))
    if root is not None:
        paths = sorted({row.get("runner") or row.get("path") for row in rows})
        for value in paths:
            digest.update(value.encode("utf-8"))
            digest.update(local_path(root, value).read_bytes())
        if any('runner' in row for row in rows):
            digest.update((root / 'agent/module.json').read_bytes())
    return digest.hexdigest()


def validate_approvals(root, data, category, id_field):
    for item_id in {row[id_field] for row in data[category]}:
        rows = [row for row in data[category] if row[id_field] == item_id]
        if len({(row["status"], row["decision_ref"]) for row in rows}) != 1:
            raise PackageError("Inconsistent approval state: " + item_id)
        status, ref = rows[0]["status"], rows[0]["decision_ref"]
        if status not in ("proposed", "accepted", "rejected"):
            raise PackageError("Invalid approval state: " + item_id)
        if status != "accepted":
            continue
        record = next((row for row in data["records"] if row["record_id"] == ref and row["kind"] == "human_decision"), None)
        if record is None:
            raise PackageError("Missing individual human decision: " + item_id)
        decision = json.loads(local_path(root, record["path"]).read_text(encoding="utf-8-sig"))
        expected = {"item_id": item_id, "category": category, "decision": "accepted", "item_sha256": item_digest(rows, root)}
        if any(decision.get(key) != value for key, value in expected.items()):
            raise PackageError("Outdated or mismatched decision: " + item_id)
        if not all(decision.get(key) for key in ("confirmed_by", "confirmed_at", "source_ref")):
            raise PackageError("Incomplete human decision: " + item_id)


def load_package(root):
    root = Path(root).resolve()
    data = {}
    for name, fields in FIELDS.items():
        filename = 'testcase' if name == 'testcases' else name
        with (root / "agent" / (filename + ".csv")).open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != fields.split(","):
                raise PackageError("Invalid columns in " + name)
            data[name] = list(reader)
            if any(None in row or None in row.values() for row in data[name]):
                raise PackageError("Invalid CSV row in " + name)
    terms = {}
    for row in data["terms"]:
        tid = row["term_id"]
        if not re.fullmatch(r"T-[A-Z0-9-]+", tid):
            raise PackageError("Invalid term ID: " + tid)
        definition = {key: value for key, value in row.items() if key != "alias"}
        if tid in terms and terms[tid]["definition_row"] != definition:
            raise PackageError("Inconsistent term: " + tid)
        terms.setdefault(tid, {"definition_row": definition, "aliases": []})
        terms[tid]["aliases"].append(row["alias"])
    data["term_map"] = {
        tid: dict(item["definition_row"], aliases=item["aliases"])
        for tid, item in terms.items()
    }
    index = json.loads((root / "agent/source_nodes.json").read_text(encoding="utf-8"))
    data["source_nodes"] = {node["id"]: node for node in index["nodes"]}
    stale = []
    for item in index["files"]:
        path = local_path(root, item["path"])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            stale.append(item["path"])
    data["stale_sources"] = stale
    for term in data["term_map"].values():
        node = data["source_nodes"].get(term["ast_id"])
        if not node or node["path"] != term["path"] or node["symbol"] != term["symbol"] or term["term"] != term["symbol"]:
            raise PackageError("Term must reference its source declaration: " + term["term_id"])
        term["source_node"] = node
    for name in ("testcases", "records", "gates"):
        id_field = {"testcases": "case_id", "records": "record_id", "gates": "gate_id"}[name]
        seen = {}
        for row in data[name]:
            if row["term_id"] not in terms:
                raise PackageError("Unknown term in " + name + ": " + row["term_id"])
            # Gates may associate several cases; other rows vary only by term.
            identity = row[id_field]
            if not identity:
                raise PackageError("Empty ID in " + name)
            if name == "gates":
                identity += "/" + row["case_id"] + "/" + row["term_id"]
            definition = {key: value for key, value in row.items() if key != "term_id"}
            if identity in seen and seen[identity] != definition:
                raise PackageError("Inconsistent record: " + identity)
            seen[identity] = definition
    cases = {row["case_id"] for row in data["testcases"]}
    for row in data["gates"]:
        if row["case_id"] and row["case_id"] not in cases:
            raise PackageError("Broken gate reference: " + row["gate_id"])
        if row["selection"] not in ("always", "conditional"):
            raise PackageError("Invalid gate state: " + row["gate_id"])
        runner = local_path(root, row["runner"])
        if not runner.is_relative_to(root / "agent/gates") or not runner.is_file():
            raise PackageError("Gate requires an implemented gates script: " + row["gate_id"])
        args = json.loads(row["args"])
        if not isinstance(args, list) or not all(isinstance(value, str) for value in args):
            raise PackageError("Invalid gate arguments: " + row["gate_id"])
    for row in data["records"]:
        if row["case_id"] and row["case_id"] not in cases:
            raise PackageError("Broken case reference: " + row["record_id"])
    validate_approvals(root, data, "testcases", "case_id")
    validate_approvals(root, data, "gates", "gate_id")
    for name in ("terms", "testcases", "records"):
        for row in data[name]:
            local_path(root, row["path"])
    for name in ("GOAL.md", "DESIGN.md"):
        data[name] = (root / name).read_text(encoding="utf-8-sig")
        unknown = set(TERM_REF.findall(data[name])) - set(terms)
        if unknown:
            raise PackageError("Broken exact references: " + ", ".join(sorted(unknown)))
        known_nodes = {node["qualified"] for node in index["nodes"]}
        unknown_nodes = set(NODE_REF.findall(data[name])) - known_nodes
        if unknown_nodes:
            raise PackageError("Broken design node references: " + ", ".join(sorted(unknown_nodes)))
    paths = [root / name for name in ("GOAL.md", "DESIGN.md", "AGENTS.md")]
    paths.extend(path for path in (root / "agent").rglob("*")
                 if path.is_file() and path.suffix in (".md", ".csv", ".py", ".json"))
    paths.extend(path for path in (root / "agent/gates").rglob("*.py"))
    data["revision"] = fingerprint(root, paths)
    data["source_revision"] = fingerprint(root, module_config.source_files(root))
    return data


def unique(rows, field):
    return list({row[field]: row for row in rows}.values())


def match_score(term, query):
    words = [term["term_id"], term["term"], *term["aliases"], term["symbol"], term["definition"]]
    query = query.casefold().strip()
    if not query:
        return 1.0, "catalog"
    scores = []
    for word in words:
        word = word.casefold()
        if query == word:
            scores.append((1.0, "exact"))
        elif query in word:
            scores.append((0.9, "substring"))
        else:
            tokens = query.split()
            if len(tokens) > 1 and all(token in word for token in tokens):
                scores.append((0.8, "tokens"))
            scores.append((difflib.SequenceMatcher(None, query, word).ratio(), "similarity"))
    return max(scores)


def query(root, level, text="", ref="", offset=0, limit=10, revision="", text_offset=0):
    data = load_package(root)
    result = {"level": level, "moduleRoot": str(root), "sourceRevision": data["source_revision"],
              "revision": data["revision"], "status": "ok", "items": [], "terms": [], "next": []}
    if data["stale_sources"]:
        return dict(result, status="stale_source_index", files=data["stale_sources"], message="Rebuild agent/source_nodes.json and term bindings with build_source_index.py.")
    if revision and revision != data["revision"]:
        return dict(result, status="stale_revision", message="Re-query without --revision.")
    known = set(data["term_map"])
    known.update(row["case_id"] for row in data["testcases"])
    known.update(row["record_id"] for row in data["records"])
    if ref and ref not in known:
        return dict(result, status="unknown_ref", message="Use level 2 to discover term and case IDs.")
    term_ids = {ref} & set(data["term_map"])
    for name, field in (("testcases", "case_id"), ("records", "record_id")):
        term_ids.update(row["term_id"] for row in data[name] if row[field] == ref)
    if level in (0, 1):
        source = "GOAL.md" if level == 0 else "DESIGN.md"
        sections = re.split(r"(?=^## )", data[source], flags=re.MULTILINE)
        items = [{"path": source, "text": section.strip()} for section in sections if section.strip()]
        if ref:
            items = [item for item in items if term_ids.intersection(TERM_REF.findall(item["text"]))]
        if text:
            items = [item for item in items if text.casefold() in item["text"].casefold()]
    elif level == 2:
        items = []
        for tid, term in data["term_map"].items():
            score, reason = match_score(term, text)
            if score < 0.45 or (ref and tid not in term_ids):
                continue
            cases = unique([row for row in data["testcases"] if row["term_id"] == tid], "case_id")
            gates = [row for row in data["gates"] if row["term_id"] == tid]
            items.append(dict(term, score=round(score, 3), matchReason=reason, testcases=cases, gates=gates))
        items.sort(key=lambda item: (-item["score"], item["term_id"]))
        result["baselineGates"] = unique([row for row in data["gates"] if row["selection"] == "always"], "gate_id")
    else:
        rows = data["records"]
        if ref in {row["record_id"] for row in rows}:
            rows = [row for row in rows if row["record_id"] == ref]
        elif ref:
            rows = [row for row in rows if row["record_id"] == ref or row["case_id"] == ref or row["term_id"] in term_ids]
        if text:
            rows = [row for row in rows if text.casefold() in " ".join(row.values()).casefold()]
        items = unique(rows, "record_id")
    result["total"] = len(items)
    result["items"] = items[offset:offset + limit]
    result["truncated"] = offset + limit < len(items)
    args = {"level": level, "query": text, "ref": ref, "limit": limit, "revision": data["revision"]}
    if result["truncated"]:
        result["next"].append({"why": "下一页", "args": dict(args, offset=offset + limit)})
    if level in (0, 1):
        ids = set(TERM_REF.findall("\n".join(item["text"] for item in result["items"])))
        result["terms"] = [data["term_map"][tid] for tid in sorted(ids)]
        names = set(NODE_REF.findall("\n".join(item["text"] for item in result["items"])))
        result["source_nodes"] = [node for node in data["source_nodes"].values()
                                  if node["qualified"] in names and node["kind"] == "function_definition"]
        result["next"].append({"why": "读取设计" if level == 0 else "查找相关术语、用例和门禁",
                               "args": {"level": level + 1, "ref": ref, "revision": data["revision"]}})
    elif level == 2:
        for item in result["items"]:
            result["next"].append({"why": "读取相关工程记录", "args": {"level": 3, "ref": item["term_id"], "revision": data["revision"]}})
    else:
        for item in result["items"]:
            path = local_path(root, item["path"])
            if not path.is_file():
                item["evidenceStatus"] = "evidence_missing"
                continue
            content = path.read_text(encoding="utf-8-sig")
            item["text"] = content[text_offset:text_offset + 4000]
            item["textTruncated"] = text_offset + 4000 < len(content)
            item["evidenceStatus"] = "available"
            if item["textTruncated"]:
                result["next"].append({"why": "继续读取记录", "args": {"level": 3, "ref": item["record_id"], "text_offset": text_offset + 4000, "revision": data["revision"]}})
    if not result["items"]:
        result["status"] = "empty"
        result["next"] = [{"why": "放宽查询，查看术语目录", "args": {"level": 2}}]
    return result


def check(root):
    data = load_package(root)
    if data["stale_sources"]:
        raise PackageError("Stale source index: " + ", ".join(data["stale_sources"]))
    for name in ("terms", "testcases", "records"):
        for row in data[name]:
            path = local_path(root, row["path"])
            if not path.is_file():
                raise PackageError("Missing file: " + row["path"])
            if name == "terms" and row["symbol"] not in path.read_text(encoding="utf-8-sig"):
                raise PackageError("Missing symbol: " + row["symbol"])
            if name == "testcases":
                source = path.read_text(encoding="utf-8-sig")
                names = module_config.registered_tests(source)
                if path.suffix != ".cpp" or row["name"] not in names:
                    raise PackageError("Missing registered UE AutomationTest: " + row["name"])
    return {"status": "ok", "revision": data["revision"], "terms": len(data["term_map"]),
            "testcases": len(unique(data["testcases"], "case_id")), "message": "Package references verified; runtime tests are recorded separately."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level", type=int, choices=range(4), default=0)
    parser.add_argument("--query", default="")
    parser.add_argument("--ref", default="")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--revision", default="")
    parser.add_argument("--text-offset", type=int, default=0)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        if args.offset < 0 or args.text_offset < 0 or not 1 <= args.limit <= 50:
            raise PackageError("Offsets must be nonnegative; limit must be 1..50.")
        result = check(ROOT) if args.check else query(ROOT, args.level, args.query, args.ref, args.offset, args.limit, args.revision, args.text_offset)
    except (ValueError, OSError) as error:
        result = {"status": "invalid_package", "message": str(error)}
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in ("ok", "empty") else 2


if __name__ == "__main__":
    sys.exit(main())
