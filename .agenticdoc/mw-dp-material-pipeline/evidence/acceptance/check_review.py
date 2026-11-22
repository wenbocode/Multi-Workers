"""Read-only structural gate for this key's independent acceptance evidence."""

import argparse
import collections
import hashlib
import json
import pathlib
import re


STAGES = {"decision_book", "model_input", "model_return", "pm_decision"}
PASSING = {"matched", "justified-change", "expected-rejection"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("report", "spec", "evidence-index", "reference-index"):
        parser.add_argument("--" + name, type=pathlib.Path, required=True)
    args = parser.parse_args()
    index = json.loads(args.evidence_index.read_bytes())
    key = args.spec.resolve().parent
    reference = json.loads(args.reference_index.read_bytes())
    comparison_file = key / index["comparison"]
    comparison = json.loads(comparison_file.read_bytes())
    expected = {(item["case_id"], stage) for item in reference["cases"] for stage in STAGES}
    actual = [(row["case_id"], row["stage_id"]) for row in comparison["rows"]]
    assert len(actual) == 36 and set(actual) == expected
    assert comparison["cohorts"] == reference["cohorts"]
    assert hashlib.sha256(args.spec.read_bytes()).hexdigest() == comparison["spec_sha256"] == index["spec_sha256"]
    assert comparison["source_file_sha256"] == index["source_file_sha256"]
    for file, expected_hash in comparison["source_file_sha256"].items():
        assert hashlib.sha256((key.parents[1] / file).read_bytes()).hexdigest() == expected_hash
    for row in comparison["rows"]:
        assert hashlib.sha256((key / row["reference_path"]).read_bytes()).hexdigest() == row["reference_sha256"]
        assert row["reference_result"] == "matched" and row["field_checks"] and row["ac_ids"] and row["vc_ids"]
        for link in row["evidence_refs"]:
            path = (key / link).resolve(strict=True)
            assert path.is_relative_to(key) and path.is_file()
    stats = collections.Counter(row["status"] for row in comparison["rows"])
    review = args.report.read_text(encoding="utf-8") if args.report.is_file() else ""
    verified = {
        criterion
        for line in review.splitlines() if line.startswith("|") and re.search(r"\|\s*met\s*\|", line)
        for criterion in re.findall(r"\b(?:AC|VC)-\d{3}\b", line)
    }
    ac017 = index.get("ac_observations", {}).get("AC-017", {})
    if ac017.get("status") == "signed-off":
        scoped_review = (key / ac017["independent_review"]).resolve(strict=True)
        assert scoped_review.is_relative_to(key) and scoped_review.is_file()
        assert hashlib.sha256(scoped_review.read_bytes()).hexdigest() == ac017["independent_review_sha256"]
        assert ac017["signed_spec_sha256"] == index["spec_sha256"]
        assert ac017["signed_comparison_sha256"] == hashlib.sha256(comparison_file.read_bytes()).hexdigest()
        assert "| AC-017 | VC-017 | met |" in scoped_review.read_text(encoding="utf-8")
        verified.update({"AC-017", "VC-017"})
    needed = {f"{kind}-{number:03}" for kind in ("AC", "VC") for number in range(1, 19)}
    print(json.dumps({"rows": len(actual), "reference_matched": sum(r["reference_result"] == "matched" for r in comparison["rows"]),
                      "implementation": stats, "independent_review_present": bool(review.strip()),
                      "independent_criteria_met": len(needed & verified)}, ensure_ascii=False))
    return 2 if not needed <= verified or set(stats) - PASSING else 0


if __name__ == "__main__":
    raise SystemExit(main())
