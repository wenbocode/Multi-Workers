"""Rebuild source syntax nodes; requires tree-sitter and tree-sitter-cpp."""
import ast
import argparse
import csv
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
import sys
import module_config

ROOT = Path(__file__).resolve().parents[1]


def mask_reflection_macros(source):
    """Blank known UE annotation calls while preserving byte/line offsets."""
    result = bytearray(source)
    spans = []
    pattern = rb"\b(?:UENUM|USTRUCT|UCLASS|UPROPERTY|UFUNCTION|UMETA|GENERATED_BODY)\s*\("
    for match in re.finditer(pattern, source):
        depth, position, quote = 1, match.end(), None
        while position < len(source) and depth:
            char = source[position]
            if quote:
                if char == 92:
                    position += 2
                    continue
                if char == quote:
                    quote = None
            elif char in (34, 39):
                quote = char
            elif char == 40:
                depth += 1
            elif char == 41:
                depth -= 1
            position += 1
        if depth:
            raise ValueError("Unclosed UE annotation")
        for index in range(match.start(), position):
            if result[index] not in (10, 13):
                result[index] = 32
        spans.append([match.start(), position])
    return bytes(result), spans


def build(root=ROOT):
    sources = module_config.source_files(root)
    cpp = [p for p in sources if p.suffix in ('.h', '.hpp', '.cpp', '.cc')]
    if cpp:
        from tree_sitter import Language, Parser
        import tree_sitter_cpp
        language = Language(tree_sitter_cpp.language())
    nodes, files = [], []
    for path in cpp:
        source = path.read_bytes()
        normalized, spans = mask_reflection_macros(source)
        tree = Parser(language).parse(normalized)
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(source).hexdigest()
        errors = []

        def text(node):
            return normalized[node.start_byte:node.end_byte].decode("utf-8") if node else ""

        def declarator_name(node):
            while node and node.type not in ("identifier", "field_identifier", "qualified_identifier", "destructor_name"):
                node = node.child_by_field_name("declarator")
            return text(node)

        def walk(node, scope=""):
            if node.type == "ERROR" or node.is_missing:
                errors.append({"kind": node.type, "line": source.count(b"\n", 0, node.start_byte) + 1})
            name = ""
            if node.type in ("class_specifier", "struct_specifier", "enum_specifier", "namespace_definition", "enumerator"):
                name = text(node.child_by_field_name("name"))
            elif node.type in ("function_definition", "field_declaration", "declaration"):
                name = declarator_name(node.child_by_field_name("declarator"))
            qualified = name if "::" in name or not scope else scope + "::" + name
            if name:
                line = source.count(b"\n", 0, node.start_byte) + 1
                nodes.append({"id": relative + "#" + node.type + ":" + qualified + ":" + str(line),
                              "symbol": name.split("::")[-1], "qualified": qualified, "kind": node.type,
                              "path": relative, "line": line, "end_line": source.count(b"\n", 0, node.end_byte) + 1,
                              "start_byte": node.start_byte, "end_byte": node.end_byte,
                              "source_sha256": digest, "has_error": node.has_error,
                              "excerpt": source[node.start_byte:min(node.end_byte, node.start_byte + 240)].decode("utf-8", errors="ignore")})
            if node.type in ("class_specifier", "struct_specifier", "namespace_definition") and name:
                scope = qualified
            for child in node.named_children:
                walk(child, scope)

        walk(tree.root_node)
        files.append({"path": relative, "sha256": digest, "masked_annotations": len(spans), "parse_errors": errors})
    python_paths = sorted({root / "agent/ask.py", *(p for p in sources if p.suffix == '.py')})
    for path in python_paths:
        source = path.read_bytes()
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(source).hexdigest()
        class Visitor(ast.NodeVisitor):
            def __init__(self): self.scope = []
            def visit_definition(self, node):
                qualified = '::'.join([*self.scope, node.name])
                nodes.append({"id": relative + '#' + type(node).__name__ + ':' + qualified,
                              "symbol": node.name, "qualified": qualified, "kind": type(node).__name__,
                              "path": relative, "line": node.lineno, "end_line": node.end_lineno,
                              "source_sha256": digest, "has_error": False,
                              "excerpt": ast.get_source_segment(source.decode('utf-8-sig'), node).splitlines()[0]})
                self.scope.append(node.name)
                self.generic_visit(node)
                self.scope.pop()
            visit_FunctionDef = visit_definition
            visit_AsyncFunctionDef = visit_definition
            visit_ClassDef = visit_definition
        Visitor().visit(ast.parse(source))
        files.append({"path": relative, "sha256": digest, "masked_annotations": 0, "parse_errors": []})
    return {"schemaVersion": 1, "parser": {"cpp": "tree-sitter-cpp " + version("tree-sitter-cpp") if cpp else "unused",
             "runtime": "tree-sitter " + version("tree-sitter") if cpp else "unused", "python": "stdlib ast"},
            "scope": "Syntax nodes; UE reflection annotations blanked with offsets preserved. Unresolved macros and errors are listed per file. No C++ type resolution.",
            "files": files, "nodes": nodes}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare regenerated syntax index without writing files")
    args = parser.parse_args()
    result = build()
    index_path = ROOT / "agent/source_nodes.json"
    if args.check:
        if json.loads(index_path.read_text(encoding="utf-8")) != result:
            raise SystemExit("Source syntax index differs; rebuild required")
        print("Source syntax index reproduces exactly")
        raise SystemExit(0)
    index_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"files": len(result["files"]), "nodes": len(result["nodes"]),
                      "parse_errors": sum(len(item["parse_errors"]) for item in result["files"])}))
