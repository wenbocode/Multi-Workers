def _lookup_material(material, dotted):
    """Value at a dotted material path, or ``_MISSING`` when it is absent."""
    current = material
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


_MISSING = object()


def _material_anchor(value):
    """First real prose leaf of a material value (candidate ids are keys, not text)."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "id":
                continue
            anchor = _material_anchor(item)
            if anchor:
                return anchor
        return ""
    if isinstance(value, (list, tuple)):
        for item in value:
            anchor = _material_anchor(item)
            if anchor:
                return anchor
        return ""
    return ""


def _assert_case_materials(dp: str, material: dict) -> None:
    """The design §2 business facts of one entry, checked per entry."""
    for field in DESIGN_STATE_FIELDS[dp]:
        assert field in material, f"{dp}: design §2 field {field!r} is missing"
        value = material[field]
        assert value not in (None, "", [], {}), f"{dp}.{field} must carry real material"
    if dp == "dp-w-type":
        for field in ("task_goal", "task_requirements", "task_deliverables"):
            assert isinstance(material[field], str), f"{dp}.{field} is a verbatim string"
        # ``false`` is a real fact, and it is never an image-capability proof.
        assert material["images_required"] is False
    if dp == "dp-pm-steer":
        background = material["pm_decision_background"]
        assert isinstance(background, str) and len(background) > 40
        # The case keeps the registry questions: it never rewrites them and never
        # introduces a "continue" label (design D003 / §4.3).
        for forbidden in ("questions", "choices", "labels", "instructions", "checkpoint_action"):
            assert forbidden not in material, f"dp-pm-steer material must not redefine {forbidden!r}"
        assert "continue" not in json.dumps(material, ensure_ascii=False)
        worker_execution = material["worker_execution"]
        assert isinstance(worker_execution, str) and worker_execution
        assert "时间预算" in worker_execution
    if dp == "dp-w-check-task":
        investigation = material["investigation"]
        assert set(investigation) == {
            "unknown",
            "evidence_source",
            "budget",
            "stop_condition",
        }
        # fire-and-forget: the worker judgement never waits for a PM reply.
        assert "等待" not in json.dumps(material, ensure_ascii=False)
    if dp == "dp-QG":
        assert isinstance(material["review_evidence"], list) and material["review_evidence"]
        # reopen needs the substantive basis problem; this material carries none,
        # so the case can only exercise pass/fix (the branch gate below proves it).
        assert "basis_issue" not in material
    if dp == "dp-gate-approve":
        note = material["pm_note"]
        assert set(note) == {"subject", "planned_action", "basis"}
        assert set(note["basis"]) == {"goal", "evidence", "budget", "authority"}
        assert isinstance(material["condition_evidence"], list) and material["condition_evidence"]
    if dp == "dp-sign-key":
        evidence = material["verification_evidence"]
        assert isinstance(evidence, dict) and set(evidence) == {"verified", "unverified"}
        assert isinstance(evidence["verified"], list) and evidence["verified"]
        assert isinstance(evidence["unverified"], list) and evidence["unverified"]
        assert isinstance(material["unfinished_impact"], list) and material["unfinished_impact"]
    if dp == "dp-auto":
        background = material["background"]
        assert set(background) == {
            "task_goal",
            "current_state",
            "tried",
            "unknowns",
            "constraints",
        }
        options = material["handling_options"]
        assert isinstance(options, list) and len(options) >= 2, "dp-auto needs >= 2 candidates"
        ids = []
        labels = []
        for option in options:
            assert set(option) == {
                "id",
                "label",
                "description",
                "consequence",
                "risk",
                "conditions",
            }
            assert all(option[name].strip() for name in option)
            ids.append(option["id"])
            labels.append(option["label"])
        assert len(set(ids)) == len(ids), "dp-auto candidate ids must be distinguishable"
        assert len(set(labels)) == len(labels), "dp-auto candidate labels must be distinct"
        assert all(len(label) <= 80 for label in labels)
        # Free ids: the legacy contiguous cN scheme is history, not this contract.
        assert ids != [f"c{index}" for index in range(1, len(ids) + 1)]
        assert all(not re.fullmatch(r"c\d", candidate) for candidate in ids)
    if dp == "dp-route":
        assert set(material) == {"decision_actor", "decision_object", "question"}


def _assert_evidence_points_at_the_material(dp: str, material: dict, book: dict) -> None:
    """Every required material path has a ``path:line`` row inside the copy.

    The recorded line must really carry the material text, so the provenance is
    not a decorative reference: this test re-reads the generator source.
    """
    evidence = book["notes"]["evidence"]
    required = decision_book.required_state_paths(dp)
    optional = decision_book.optional_state_paths(dp)
    assert set(required) <= set(evidence), f"{dp}: required evidence rows are missing"
    assert set(evidence) <= set(required) | set(optional), f"{dp}: stray evidence rows"
    generator_rel = "packages/multi-workers/scripts/build_decide_cases.py"
    lines = GENERATOR_PATH.read_text(encoding="utf-8").splitlines()
    for path, reference in evidence.items():
        assert reference.startswith(generator_rel + ":"), (dp, path, reference)
        line_number = int(reference.rsplit(":", 1)[1])
        assert 1 <= line_number <= len(lines), reference
        anchor = _material_anchor(_lookup_material(material, path))
        assert anchor, f"{dp}.{path} has no text anchor"
        assert anchor[:8] in lines[line_number - 1], (
            f"{dp}.{path} evidence points at a line that does not carry the material"
        )


def test_eight_offline_cases_are_complete_schema3_and_contract_shaped():
    module = _generator_module()
    assert set(CASE_FILES) == set(module.CASE_IDS), "the generator owns exactly eight case ids"
    assert not set(module.CASE_IDS) & set(LEGACY_CASE_FILES), "no legacy id is generated"
    cases = module.build_cases()
    assert set(cases) == set(CASE_FILES)

    for dp, shell in cases.items():
        assert set(shell) == {"case_version", "dp", "title", "note", "book", "questions"}, (
            f"{dp}: the case includes the complete observation questions"
        )
        assert shell["questions"] == decision_points.questions_map(dp)
        _assert_no_placeholders(shell["questions"], dp + ".questions")
        assert shell["case_version"] == 1
        assert shell["dp"] == dp
        assert isinstance(shell["title"], str) and len(shell["title"]) > 8
        assert isinstance(shell["note"], str) and len(shell["note"]) > 20
        _assert_no_placeholders({"title": shell["title"], "note": shell["note"]}, dp)

        book = shell["book"]
        assert set(book) <= set(decision_book.BOOK_TOP_LEVEL_KEYS)
        assert book["schema_version"] == decision_book.BOOK_SCHEMA_VERSION == 3
        assert book["decision_point"] == dp
        assert "state" not in book, "a schema-3 book never carries the legacy state shape"
        material = book["material"]
        preparation = book["preparation"]
        meta = book["meta"]
        assert isinstance(material, dict) and isinstance(preparation, dict)
        _assert_case_materials(dp, material)
        _assert_no_placeholders(material, dp)
        _assert_no_placeholders(preparation, dp + ".preparation")

        # Local identity: exact closed key set and the entry's real initiator role.
        assert set(meta) == set(decision_book.META_KEYS)
        assert all(isinstance(value, str) and value.strip() for value in meta.values())
        assert not decision_points.role_issues(dp, meta["actor_role"]), dp

        # Complete: every string leaf is real prose, not a skeleton value
        # (candidate ids are keys, not material, so they are exempt).
        for path, text in _iter_texts(material, dp):
            if path.endswith(".id"):
                assert text.strip(), f"{path} must carry a candidate id"
                continue
            assert len(text.strip()) >= 8, f"{path} looks like a stub ({text!r})"

        # The title/note shell never enters the book.
        serialised = json.dumps(book, ensure_ascii=False)
        assert shell["title"] not in serialised
        assert shell["note"] not in serialised

        # The existing no-truncation budget gate applies to the send payload.
        payload = {
            "material": decision_points.model_state_for(dp, material),
            "preparation": preparation,
        }
        encoded = decision._encode_state(payload)
        assert len(encoded) <= decision_points.MAX_STATE_BYTES, (
            f"{dp}: send payload is {len(encoded)} bytes, the existing budget is "
            f"{decision_points.MAX_STATE_BYTES}; shorten the material instead of truncating"
        )

        _assert_evidence_points_at_the_material(dp, material, book)
        for field in DESIGN_STATE_FIELDS[dp]:
            assert any(
                path == field or path.startswith(field + ".") for path in book["notes"]["evidence"]
            ) or field in {"images_required"}, (
                f"{dp}: design §2 field {field!r} has no evidence entry"
            )


def test_dp_pm_steer_case_keeps_the_registry_question_vocabulary():
    point = decision_points.get_decision_point("dp-pm-steer")
    questions = point.questions
    assert [question["id"] for question in questions] == ["checkpoint_action"]
    choices = list(questions[0]["choices"])
    assert choices == DP2_CHOICES
    assert "continue" not in choices
    assert set(questions[0]["labels"]) == set(DP2_CHOICES)
    assert "继续" in questions[0]["instructions"]
    # The case material keeps the original goal/requirements instead of narrowing
    # them for the checkpoint decision.
    material = _generator_module().build_case("dp-pm-steer")["book"]["material"]
    assert material["task_goal"].startswith("给 mw decide monitor 增加旧记录只读筛选")
    assert "不改其余入口的既有契约" in material["task_requirements"]


def test_eight_cases_pass_the_offline_registry_typed_check():
    """Offline ``check_book`` (no credential, no model) accepts 8/8 cases.

    The gate runs with the *implementation copy* as its repository root, so the
    ``path:line`` evidence resolves inside the copy and never against the live
    tree. The real HTTP body/edit assertion still needs the monitor route
    migration and remains a separate integration step.
    """
    module = _generator_module()
    failures = {}
    for dp, case in module.build_cases().items():
        issues = decision_book.check_book(case["book"], repo_root=REPO_ROOT)
        if issues:
            failures[dp] = [(issue.code, issue.path, issue.detail) for issue in issues]
    assert failures == {}, failures


def test_case_evidence_is_really_checked_and_resolves_inside_the_copy(tmp_path):
    """The evidence gate is not vacuous: a wrong root really refuses the book."""
    module = _generator_module()
    cases = module.build_cases()
    for dp, case in cases.items():
        evidence = case["book"]["notes"]["evidence"]
        for reference in evidence.values():
            relative, _, line = reference.rpartition(":")
            resolved = (REPO_ROOT / relative).resolve()
            assert resolved.is_file(), reference
            assert REPO_ROOT in resolved.parents
            assert resolved == GENERATOR_PATH.resolve()
            int(line)

    empty_repo = tmp_path / "empty-repo"
    empty_repo.mkdir()
    issues = decision_book.check_book(
        cases["dp-sign-key"]["book"], repo_root=empty_repo
    )
    paths = {issue.path for issue in issues}
    assert "notes.evidence.delivery_goal" in paths, issues
    assert any(issue.code == "book-evidence" for issue in issues)


def test_each_case_prepares_a_real_basis_for_every_supported_choice():
    """Every choice the material supports has exactly one prepared reason (D012A).

    The model selects one of these items in the same call; the catalog is a
    preparation input, so a failure reason, a probability or the PM note can
    never impersonate it.
    """
    module = _generator_module()
    for dp, case in module.build_cases().items():
        book = case["book"]
        material = book["material"]
        preparation = book["preparation"]
        meta = book["meta"]
        assert set(preparation) == {"basis_catalog", "prepared_at"}
        assert preparation["prepared_at"].endswith("+00:00")

        legal = decision_points.resolve_entry_choices(dp, material)
        assert legal, dp
        supported = [
            choice
            for choice in legal
            if not decision_points.entry_choice_issues(dp, choice, material)
        ]
        covered = {
            choice for item in preparation["basis_catalog"] for choice in item["applies_to"]
        }
        assert covered == set(supported), dp
        for item in preparation["basis_catalog"]:
            assert set(item) == {"id", "text", "material_refs", "applies_to"}
            assert item["material_refs"], dp
            for choice in item["applies_to"]:
                issues = decision_points.prepared_request_issues(
                    dp,
                    material,
                    preparation,
                    actor_role=meta["actor_role"],
                    choice=choice,
                    basis_id=item["id"],
                )
                assert issues == (), (dp, choice, issues)


def test_dp_w_type_case_keeps_four_candidates_and_the_image_gate():
    module = _generator_module()
    case = module.build_case("dp-w-type")
    material = case["book"]["material"]
    point = decision_points.get_decision_point("dp-w-type")
    assert list(point.questions[0]["choices"]) == ["coding", "research", "review", "vision"]
    # The case states a real fact ("no image reading"); that is never a proof of
    # image capability, so a vision dispatch stays refused by the hard gate.
    assert material["images_required"] is False
    assert decision_points.vision_dispatch_issues(material, "coding", "proven") == ()
    vision = decision_points.vision_dispatch_issues(material, "vision", "proven")
    assert ("vision", "requires images_required=true on the real dispatch material") in vision


def test_dp_w_check_task_case_keeps_three_branches_and_needs_no_pm_wait():
    module = _generator_module()
    book = module.build_case("dp-w-check-task")["book"]
    material = dict(book["material"])
    point = decision_points.get_decision_point("dp-w-check-task")
    assert list(point.questions[0]["choices"]) == ["continue", "terminate", "investigate"]

    without_plan = dict(material)
    without_plan.pop("investigation")
    issues = decision_points.entry_choice_issues("dp-w-check-task", "investigate", without_plan)
    assert ("investigation.unknown", "required by the investigate branch (bounded evidence plan)") in issues
    for choice in ("continue", "terminate", "investigate"):
        assert decision_points.entry_choice_issues("dp-w-check-task", choice, material) == ()
    # fire-and-forget: no field asks the worker to block on a PM answer.
    assert "等待" not in json.dumps(material, ensure_ascii=False)


def test_dp_sigkey_qg_and_gate_entries_refuse_their_own_missing_branch_material():
    """Branch-conditional material is required, never defaulted (AC-043)."""
    module = _generator_module()
    qg = dict(module.build_case("dp-QG")["book"]["material"])
    reopen = decision_points.entry_choice_issues("dp-QG", "reopen", qg)
    assert ("basis_issue", "required by reopen: name the substantive basis problem") in reopen

    with_issue = dict(qg)
    with_issue["basis_issue"] = "验收要求与设计正文冲突，需要重新确认口径。"
    assert decision_points.entry_choice_issues("dp-QG", "reopen", with_issue) == ()
    pass_with_issue = decision_points.entry_choice_issues("dp-QG", "pass", with_issue)
    assert ("basis_issue", "pass cannot be combined with an unresolved basis problem") in pass_with_issue
    assert decision_points.entry_choice_issues("dp-QG", "pass", qg) == ()

    gate = dict(module.build_case("dp-gate-approve")["book"]["material"])
    no_authority = json.loads(json.dumps(gate, ensure_ascii=False))
    no_authority["pm_note"]["basis"].pop("authority")
    gate_issues = decision_points.entry_material_issues("dp-gate-approve", no_authority)
    assert ("pm_note.basis.authority", "must be a non-empty string") in gate_issues
    # No default gate answer: a missing selection is refused, not approve.
    assert decision_points.entry_choice_issues("dp-gate-approve", None, gate) == (
        ("choice", "missing selection: no default candidate is applied"),
    )


def test_dp_sign_key_case_keeps_the_four_parts_and_three_arrays():
    module = _generator_module()
    book = module.build_case("dp-sign-key")["book"]
    material = dict(book["material"])
    assert set(material) == {
        "delivery_goal",
        "actual_completion",
        "verification_evidence",
        "unfinished_impact",
    }
    for choice in ("finalize", "continue", "user-confirm"):
        assert decision_points.entry_choice_issues("dp-sign-key", choice, material) == ()

    # AC-051: [] is the real "none"; null/missing can never be upgraded to it.
    empty = json.loads(json.dumps(material, ensure_ascii=False))
    empty["verification_evidence"]["verified"] = []
    empty["verification_evidence"]["unverified"] = []
    empty["unfinished_impact"] = []
    assert decision_points.sign_key_material_issues(empty) == ()

    nulled = json.loads(json.dumps(material, ensure_ascii=False))
    nulled["verification_evidence"]["verified"] = None
    paths = {path for path, _detail in decision_points.sign_key_material_issues(nulled)}
    assert "verification_evidence.verified" in paths

    missing = json.loads(json.dumps(material, ensure_ascii=False))
    missing.pop("unfinished_impact")
    paths = {path for path, _detail in decision_points.sign_key_material_issues(missing)}
    assert "unfinished_impact" in paths


def test_dp_auto_case_uses_free_form_pm_candidates_and_invents_nothing():
    module = _generator_module()
    case = module.build_case("dp-auto")
    book = case["book"]
    material = book["material"]
    candidates = material["handling_options"]
    prepared = [candidate["id"] for candidate in candidates]

    # The registry-derived enum *is* the prepared set (no second candidate copy).
    assert decision_points.resolve_entry_choices("dp-auto", material) == tuple(prepared)
    assert "dynamic_choices" not in json.dumps(material, ensure_ascii=False)
    assert case["questions"] == decision_points.questions_map("dp-auto")

    for candidate in prepared:
        issues = decision_points.prepared_request_issues(
            "dp-auto",
            material,
            book["preparation"],
            actor_role=book["meta"]["actor_role"],
            choice=candidate,
            basis_id=next(
                item["id"]
                for item in book["preparation"]["basis_catalog"]
                if candidate in item["applies_to"]
            ),
        )
        assert issues == (), (candidate, issues)

    invented = decision_points.entry_choice_issues("dp-auto", "c1", material)
    assert ("choice", "must be one of the 3 legal ids of dp-auto; invented or retired ids are refused") in invented

    single = json.loads(json.dumps(material, ensure_ascii=False))
    single["handling_options"] = single["handling_options"][:1]
    assert decision_points.entry_choice_issues("dp-auto", prepared[0], single)


def test_dp_route_case_routes_to_the_other_seven_entries_without_authorising():
    module = _generator_module()
    book = module.build_case("dp-route")["book"]
    material = book["material"]
    point = decision_points.get_decision_point("dp-route")
    targets = list(point.questions[0]["choices"])
    assert targets == [
        "dp-w-type",
        "dp-pm-steer",
        "dp-w-check-task",
        "dp-QG",
        "dp-gate-approve",
        "dp-sign-key",
        "dp-auto",
    ]
    assert "dp-route" not in targets
    assert decision_points.resolve_entry_choices("dp-route", material) == tuple(targets)

    for target in targets:
        basis = next(
            item["id"] for item in book["preparation"]["basis_catalog"] if target in item["applies_to"]
        )
        issues = decision_points.prepared_request_issues(
            "dp-route",
            material,
            book["preparation"],
            actor_role=book["meta"]["actor_role"],
            choice=target,
            basis_id=basis,
        )
        assert issues == (), (target, issues)

    # Routing to itself is refused, and the material is only the routing fact:
    # it carries no business conclusion, no release and no action field.
    assert decision_points.entry_choice_issues("dp-route", "dp-route", material) == (
        ("choice", "must be one of the 7 legal ids of dp-route; invented or retired ids are refused"),
    )
    assert set(material) == {"decision_actor", "decision_object", "question"}


def test_generator_refuses_retired_ids_and_never_writes_legacy_cases(tmp_path, monkeypatch):
    module = _generator_module()
    assert set(module.LEGACY_CASE_IDS) == set(LEGACY_CASE_FILES)
    assert "dp1.json" not in set(module.CASE_IDS.values())
    for legacy_dp in LEGACY_CASE_FILES:
        with pytest.raises(SystemExit):
            module.build_case(legacy_dp)

    out = tmp_path / "cases"
    monkeypatch.setitem(module.CASE_IDS, "dp1-dispatch-type", "dp1.json")
    with pytest.raises(SystemExit) as excinfo:
        module.build_case("dp1-dispatch-type")
    assert "retired" in str(excinfo.value)
    with pytest.raises(SystemExit):
        module.write_cases(out)
    assert not (out / "dp1.json").exists(), "a legacy case file is never written"


def test_shipped_cases_match_the_offline_generator(tmp_path):
    module = _generator_module()
    out = tmp_path / "cases"
    written = module.write_cases(out)
    assert sorted(path.name for path in written) == sorted(CASE_FILES.values())
    assert not set(path.name for path in out.glob("*.json")) & set(LEGACY_CASE_FILES.values())
    for dp, name in CASE_FILES.items():
        shipped = CASES_DIR / name
        assert shipped.is_file(), f"missing shipped case {shipped}"
        generated = (out / name).read_text(encoding="utf-8")
        assert shipped.read_text(encoding="utf-8") == generated, (
            f"{name} drifted from the offline generator; regenerate with "
            "'python scripts/build_decide_cases.py' (offline, no model, no credential)"
        )
        assert json.loads(shipped.read_text(encoding="utf-8"))["dp"] == dp


def test_legacy_cases_stay_byte_identical_read_only_history():
    for name, sha256 in LEGACY_CASE_SHA256.items():
        shipped = CASES_DIR / name
        assert shipped.is_file(), f"missing legacy case {shipped}"
        assert hashlib.sha256(shipped.read_bytes()).hexdigest() == sha256, (
            f"{name} is read-only history and must never change; the eight-case "
            "generator writes only the eight active entries"
        )
