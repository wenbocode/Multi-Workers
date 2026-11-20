"""Host-owned exact-file grants for decision evidence, never workspace writes."""

from __future__ import annotations

import hashlib
import os
import pathlib
from collections.abc import MutableMapping

import mw_common

MAX_POLICY_BYTES = 64 * 1024
MAX_READ_FILES = 64


class EvidencePolicyError(ValueError):
    """Invalid policy; messages contain no file contents or submitted values."""


def load_read_files(
    project_root: pathlib.Path,
    dependencies: MutableMapping[str, dict[str, object]],
) -> tuple[pathlib.Path, ...]:
    """Read a bounded, stable policy snapshot and retain its freshness binding.

    Paths remain lexical: canonicalizing a grant would silently authorize a
    symlink target. The source reader requires BOTH identities to match it.
    Missing policies are dependencies too, so adding one invalidates a refusal.
    """
    policy = project_root / ".mw" / "decision-evidence.yml"
    dependency: dict[str, object] = {
        "path": str(policy), "canonical_path": None, "sha256": None, "status": "missing",
    }
    dependencies[os.path.normcase(str(policy)).replace("\\", "/")] = dependency
    try:
        canonical = policy.resolve(strict=True)
    except FileNotFoundError:
        return ()
    except (OSError, RuntimeError) as exc:
        raise EvidencePolicyError("decision evidence policy cannot be resolved") from exc
    dependency.update(canonical_path=str(canonical), status="unreadable")
    try:
        before = canonical.stat()
        if not canonical.is_file():
            raise EvidencePolicyError("decision evidence policy must be a regular file")
        if before.st_size > MAX_POLICY_BYTES:
            dependency["status"] = "oversized"
            raise EvidencePolicyError("decision evidence policy exceeds the read limit")
        with canonical.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            raw = handle.read(MAX_POLICY_BYTES + 1)
            after = os.fstat(handle.fileno())
        signature = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
        if (len(raw) > MAX_POLICY_BYTES or signature(before) != signature(opened)
                or signature(before) != signature(after) or signature(before) != signature(canonical.stat())
                or policy.resolve(strict=True) != canonical):
            raise EvidencePolicyError("decision evidence policy changed while reading")
        dependency["sha256"] = hashlib.sha256(raw).hexdigest()
        dependency.pop("status")
        text = raw.decode("utf-8-sig")
    except (OSError, UnicodeError, RuntimeError) as exc:
        raise EvidencePolicyError("decision evidence policy is unreadable or not UTF-8") from exc
    yaml = mw_common.yaml
    if yaml is None:
        raise EvidencePolicyError("PyYAML is required to read decision evidence policy")

    class UniqueLoader(yaml.SafeLoader):
        def construct_mapping(self, node, deep=False):
            self.flatten_mapping(node)
            result = {}
            for key_node, value_node in node.value:
                key = self.construct_object(key_node, deep=deep)
                if not isinstance(key, str) or key in result:
                    raise EvidencePolicyError("decision evidence policy has duplicate or non-string keys")
                result[key] = self.construct_object(value_node, deep=deep)
            return result

    try:
        data = yaml.load(text, Loader=UniqueLoader)
    except yaml.YAMLError as exc:
        raise EvidencePolicyError("decision evidence policy is invalid YAML") from exc
    if not isinstance(data, dict) or set(data) != {"read_files"}:
        raise EvidencePolicyError("decision evidence policy must contain only read_files")
    values = data["read_files"]
    if not isinstance(values, list) or len(values) > MAX_READ_FILES:
        raise EvidencePolicyError("decision evidence read_files must be a bounded list")
    files = []
    for value in values:
        if (not isinstance(value, str) or not value.strip()
                or any(char in value for char in "*?[]{}\x00\r\n")):
            raise EvidencePolicyError("decision evidence read_files entries must be literal file paths")
        candidate = pathlib.Path(value.replace("\\", "/"))
        candidate = pathlib.Path(os.path.abspath(project_root / candidate))
        if candidate.is_dir():
            raise EvidencePolicyError("decision evidence read_files cannot authorize directories")
        files.append(candidate)
    return tuple(files)
