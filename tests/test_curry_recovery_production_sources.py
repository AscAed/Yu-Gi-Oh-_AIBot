import json
from dataclasses import replace
import hashlib
from pathlib import Path
import stat

import pytest

from ygo_eval import curry_input_recovery_audit as recovery


def test_source_description_lookups_are_local_first():
    left = recovery._PinnedArchive(
        "same", "left.zip", "left.json", "1" * 64, "2" * 64,
        "3" * 64, 1, "head",
    )
    right = recovery._PinnedArchive(
        "same", "right.zip", "right.json", "4" * 64, "5" * 64,
        "6" * 64, 2, "head",
    )
    tree = recovery._SourceDescription(
        "root",
        archives=(left,),
        semantic_hashes=(("semantic", "a" * 64),),
        children=(recovery._SourceDescription(
            "child",
            archives=(right,),
            semantic_hashes=(("semantic", "b" * 64),),
        ),),
    )

    assert tree.archive("same") == left
    assert tree.semantic_sha256("semantic") == "a" * 64
    assert tree.child("child").archive("same") == right
    assert tree.child("child").semantic_sha256("semantic") == "b" * 64


def test_production_description_contains_complete_recursive_source_tree():
    sources = recovery._production_source_description()
    asset = sources.child("asset_audit")
    historical = asset.child("historical_chain")
    curry = historical.child("curry_baseline")
    validation = curry.child("validation_baseline")
    runner = validation.child("runner_confirmation")
    placement = runner.child("placement_confirmation")

    assert sources.role == "confirmation"
    assert asset.child("asset_audit_scope").baseline_relative == (
        "data/runtime/p1-curry-option-validation-native-2026-10-23"
    )
    assert curry.baseline_relative == (
        "data/runtime/p1-tenki-placement-validation-native-2026-10-23"
    )
    assert curry.file_sha256_role("curry_validation_acceptance") == (
        "242e0f5e1839f132d5b091963ba9917691536ae0913e7beeca6fc62635d7f4f9"
    )
    assert curry.archive("curry_native_archive").file_count == 683
    assert curry.archive("curry_final_archive").file_count == 684
    assert curry.file_sha256_role("curry_validation_prompt_stage1") == (
        "c4231531d4b9b64605303eddebf9bb757db0fa7baa02a1e6f7606dbce5ceaf76"
    )
    assert validation.baseline_relative == (
        "data/runtime/p1-tenki-runner-repair-offline-2026-10-23"
    )
    assert runner.baseline_relative == (
        "data/runtime/p1-tenki-placement-confirmation-native-2026-10-22"
    )
    assert placement.child("baseline").baseline_relative == (
        "data/runtime/p1-tenki-probe-native-2026-10-21"
    )
    assert historical.dataset_count("previous_consumed") == 26
    assert historical.dataset_count("previous_unknown") == 0
    assert historical.dataset_count("previous_ledger_count") == 7
    assert historical.dataset_count("confirmation_consumed") == 0
    assert historical.dataset_count("confirmation_unknown") == 0
    assert historical.dataset_count("current_consumed") == 6
    assert historical.dataset_count("current_unknown") == 0
    assert historical.dataset_count("historical_consumed") == 32
    assert historical.dataset_count("historical_unknown") == 0
    assert historical.dataset_count("historical_ledgers") == 9
    assert runner.dataset_count("ledger_count") == 8
    assert placement.dataset_count("ledger_count") == 7
    assert placement.child("historical_ledgers").dataset_count("consumed") == 26
    assert placement.child("historical_ledgers").dataset_count("ledger_count") == 7

    # Recursive source-mode validators must obtain per-ledger counts and
    # exclusion totals from this immutable description too.  These assertions
    # keep synthetic profiles from inheriting production values implicitly.
    expected_ledger_counts = {
        "baseline": 9,
        "state": 8,
        "terminal": 1,
        "terminal-followup": 4,
        "terminal-smoke": 2,
        "tenki-probe": 2,
        "tenki-placement": 0,
    }
    for role, count in expected_ledger_counts.items():
        assert placement.child("historical_ledgers").dataset_count(
            f"ledger_{role}_consumed"
        ) == count

    placement_old_scope = placement.child("baseline")
    assert placement_old_scope.dataset_count("placement_python_skipped") == 7
    assert placement_old_scope.dataset_count("placement_rust_ignored") == 36
    assert placement_old_scope.dataset_count("placement_examples_ignored") == 0

    confirmation = sources
    assert confirmation.file_sha256_role("acceptance") == recovery.ACCEPTANCE_SHA256
    assert confirmation.file_sha256_role("delivery") == recovery.DELIVERY_SHA256

    assert runner.semantic_sha256("runner_stage1_request") == (
        "fac2455f2b2876bc9f28666252bdc8326dcd16cf95c63335230f2d49eac9a134"
    )
    assert placement.archive("placement_native_archive").archive_path == (
        "data/runtime/p1-tenki-placement-diagnostics-offline-2026-10-22/"
        "verification/source-audit-strict-dedupe/source-native.zip"
    )
    assert placement.archive("placement_final_archive").file_count == 459
    assert placement.semantic_sha256("placement_context") == (
        "773bafe50501dd0e093b7396d24bb2198a94503212a31d6407bdcfad8f7b1d37"
    )
    assert placement.file_sha256_role("placement_identity") == (
        "d5b443434cfabf1c6328ea4ae39e7bf642518649efda1898dd7d4dc4ee8be545"
    )
    assert placement.file_sha256_role("placement_native_build") == (
        "2bdee9ce580f517ad74ce28a93ec54215cdd5c191d99bd2e87d5d9ddc93cfa9b"
    )
    assert placement.file_sha256_role("placement_transition") == (
        "adca03b129b8e17ae69165fadd00276967c9038b6c0c1efc55241f79c7051789"
    )
    assert placement.archive("placement_history_archive").file_count == 401
    assert placement.child("baseline").archive("baseline_archive").file_count == 390


def test_production_description_fixed_top_level_pins_match_module_constants():
    sources = recovery._production_source_description()
    from ygo_eval import curry_asset_binding_audit as asset_audit
    from ygo_eval import native_curry_option_validation as curry

    asset = sources.child("asset_audit")
    assert asset.file_sha256_role("asset_audit_audit") == curry.CONFIRMATION_AUDIT_SHA256
    assert asset.file_sha256_role("asset_audit_delivery") == curry.CONFIRMATION_DELIVERY_SHA256
    assert asset.dataset_count("historical_consumed") == asset_audit.HISTORICAL_CONSUMED
    assert asset.dataset_count("historical_ledgers") == asset_audit.HISTORICAL_LEDGER_COUNT

    ledger_sources = (
        sources.child("asset_audit").child("historical_chain")
        .child("curry_baseline").child("validation_baseline")
        .child("runner_confirmation").child("placement_confirmation")
        .child("historical_ledgers")
    )
    from ygo_eval.native_tenki_placement_confirmation import OLD_LEDGER_CONTRACTS

    assert ledger_sources.dataset_count("ledger_count") == len(OLD_LEDGER_CONTRACTS)
    assert ledger_sources.dataset_count("consumed") == sum(item[3] for item in OLD_LEDGER_CONTRACTS)
    assert [ledger_sources.file_sha256(path) for _, path, *_ in OLD_LEDGER_CONTRACTS] == [
        item[2] for item in OLD_LEDGER_CONTRACTS
    ]


def test_complete_production_source_description_matches_frozen_golden_digest():
    def encode(node):
        return {
            "role": node.role,
            "files": [[item.role, item.relative_path, item.sha256] for item in node.files],
            "archives": [[
                item.role, item.archive_path, item.file_list_path,
                item.archive_sha256, item.file_list_sha256, item.source_identity,
                item.file_count, item.head,
            ] for item in node.archives],
            "semantic_hashes": [list(item) for item in node.semantic_hashes],
            "archive_differences": [[role, list(paths)] for role, paths in node.archive_differences],
            "dataset_counts": [list(item) for item in node.dataset_counts],
            "baseline_relative": node.baseline_relative,
            "output_relative_v1": node.output_relative_v1,
            "output_relative_v2": node.output_relative_v2,
            "children": [encode(item) for item in node.children],
        }

    raw = json.dumps(encode(recovery._production_source_description()),
                     ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(raw).hexdigest() == "868d9bc23c3c72c27607b1425d2d623e147bc5c7c38b4628f9c77c9580672e3c"


def test_report_validation_uses_historical_dataset_counts_from_source_tree():
    sources = recovery._production_source_description()
    historical = sources.child("asset_audit").child("historical_chain")
    synthetic_history = replace(
        historical,
        dataset_counts=(
            ("historical_consumed", 4),
            ("historical_unknown", 0),
            ("historical_ledgers", 2),
        ),
    )
    asset = sources.child("asset_audit")
    synthetic_asset = replace(
        asset,
        children=tuple(
            synthetic_history if child.role == "historical_chain" else child
            for child in asset.children
        ),
    )
    synthetic_sources = replace(
        sources,
        children=tuple(
            synthetic_asset if child.role == "asset_audit" else child
            for child in sources.children
        ),
    )
    report = recovery.new_report(2, _sources=synthetic_sources)
    report["historical"] = {
        "consumed": 4,
        "unknown": 0,
        "ledger_count": 2,
        "verified_without_writable_journal": True,
        "input_set_sha256": "a" * 64,
    }

    assert recovery.validate_report(report, _sources=synthetic_sources)


def test_production_description_preserves_inventory_hash_and_nested_pins():
    sources = recovery._production_source_description()
    described = {item.relative_path: item.sha256 for item in sources.files}
    assert described["data/runtime/p1-curry-option-confirmation-native-2026-10-24/evidence-inventory.json"] == (
        "807a45e142d5b634ad25be5ac1562ac829fa9cffca62b21c7c9f71a499b3e1ea"
    )

    asset = sources.child("asset_audit")
    assert asset.archive("asset_audit_native_archive").archive_sha256 == (
        "a235cf00ee038196782e1e33992bc7719d5dce9169d56d204f5d99167a5fbbde"
    )
    assert asset.archive("asset_audit_native_archive").file_count == 498
    assert asset.archive("asset_audit_final_archive").archive_sha256 == (
        "3043c1f6a0c3128f0f9caeeda60901e4c20442f90d07ee94b36642c4dd4b040f"
    )
    assert asset.archive("asset_audit_final_archive").file_count == 499
    assert asset.file_sha256_role("asset_audit_build_record") == (
        "da933dbae09031d5646cbed1eccdcafc403e3378e071f85e70d6d4b0945429e2"
    )
    asset_scope = asset.child("asset_audit_scope")
    assert not any(path.endswith("/acceptance.json") for path in (
        item.relative_path for item in asset_scope.files
    ))
    assert not any(path.endswith("/final-build/delivery.json") for path in (
        item.relative_path for item in asset_scope.files
    ))
    assert not any(path.endswith(".stderr.bin") for path in (
        item.relative_path for item in asset_scope.files
    ))

    validation = asset.child("historical_chain").child("curry_baseline").child("validation_baseline")
    validation_root = validation.baseline_relative
    assert validation.archive("validation_final_archive").file_list_sha256 == (
        "ef1a6d1ef25fd770e608f58238c67739416bf37f370ab316dcd2a4a62a22bd3b"
    )
    assert validation.file_sha256_role("validation_runner") == (
        "6f05feb89dad8ea92d771f4fe22a8e24a9d119aa410f0f0f66a3d02024000d8c"
    )
    assert next(item.relative_path for item in validation.files if item.role == "validation_runner") == (
        f"{validation_root}/final-build/native-artifacts/tenki-placement-probe.exe"
    )

    runner = validation.child("runner_confirmation")
    assert runner.dataset_count("historical_consumed") == 26
    assert runner.dataset_count("ledger_count") == 8
    assert runner.file_sha256_role("runner_checkpoint_blob") == (
        "dfc73a5ee5702dee0c00e1e4ce47e2e953371e5d4fca9aa1fa13eaabeb0ea80d"
    )

    placement = runner.child("placement_confirmation")
    assert placement.file_sha256_role("placement_preflight_report") == (
        "76830d7e34605ecb3bed7d4f3a725b6a18bb4ab2cca95c3314d87592d274e288"
    )
    assert next(item.relative_path for item in placement.files if item.role == "placement_preflight_report") == (
        "data/runtime/p1-tenki-placement-diagnostics-offline-2026-10-22/preflight-report.json"
    )
    assert placement.archive("placement_final_archive").archive_sha256 == (
        "db9f22e75c06b183578c710b4d9ee0a9c97e0c2032bf240197a1795ea9211595"
    )
    assert placement.archive("placement_final_archive").file_count == 459
    baseline = placement.child("baseline")
    assert baseline.archive("baseline_archive").archive_path.endswith(
        "/recovery-2026-10-22/final-source.zip"
    )
    assert baseline.file_sha256_role("baseline_prompt_stage1_input") == (
        "b2b08b1f02538af815829bb1b618f948bf65fb6654755ccfba968991ea2fe913"
    )
    assert baseline.file_sha256_role("baseline_prompt_stage1_request") == (
        "08e2679fa801a1aba4dc3e0e2645bbc7f6fd495d6094b03c5fbd15141af9331c"
    )
    assert baseline.file_sha256_role("baseline_previous_manifest") == (
        "efd59421277bb88be3cb524627f230a6dff088495a747ecd7717dc78abf41773"
    )
    assert baseline.semantic_sha256("transition_new_worker_sha256") == (
        "4f2b5a7c73914f07b0bce39ed01b7f74ed9c335dba329ef3a3bf1803a6db7680"
    )
    assert baseline.semantic_sha256("curry_scope_codec_sha256") == (
        "e8f97eefcf93ef626d2ecbc785661fde2fee47b0525e110ec7aee9a185aad133"
    )
    assert baseline.semantic_sha256("transition_old_worker_sha256") == (
        "a384b35aff160049b3381f15bfc35e17cf373a1ada54986b8c884bde09c78c7e"
    )
    assert baseline.semantic_sha256("transition_new_worker_sha256") == (
        "4f2b5a7c73914f07b0bce39ed01b7f74ed9c335dba329ef3a3bf1803a6db7680"
    )
    assert baseline.semantic_sha256("curry_scope_codec_old_sha256") == (
        "224cb3fa6a7700e871d79f202e0e3def4c3b394229bb57c462191f1da470a36e"
    )
    assert baseline.file_sha256_role("baseline_transition") == (
        placement.file_sha256_role("placement_transition")
    )


def test_production_description_matches_local_confirmation_inventory():
    sources = recovery._production_source_description()
    confirmation_root = Path(sources.baseline_relative)
    baseline_path = Path(__file__).resolve().parents[1] / confirmation_root
    try:
        baseline_path.lstat()
    except FileNotFoundError:
        pytest.skip("historical evidence baseline is not present")
    assert stat.S_ISDIR(baseline_path.stat().st_mode), "baseline must be a directory"
    inventory_path = baseline_path / "evidence-inventory.json"
    assert stat.S_ISREG(inventory_path.lstat().st_mode), "inventory must be a regular file"
    inventory_bytes = inventory_path.read_bytes()
    described = {item.relative_path: item.sha256 for item in sources.files}
    assert hashlib.sha256(inventory_bytes).hexdigest() == described[
        f"{confirmation_root.as_posix()}/evidence-inventory.json"
    ]
    inventory = json.loads(inventory_bytes)
    for entry in inventory["entries"]:
        assert described[f"{confirmation_root.as_posix()}/{entry['path']}"] == entry["sha256"]
    assert len(inventory["entries"]) == 40
    assert recovery._CONFIRMATION_INVENTORY_PINS == tuple(
        (entry["path"], entry["sha256"]) for entry in inventory["entries"]
    )


def test_archive_and_semantic_pins_are_unambiguous_only_at_their_scope():
    sources = recovery._production_source_description()
    asset_scope = sources.child("asset_audit").child("asset_audit_scope")
    curry_history = (
        sources.child("asset_audit").child("historical_chain")
        .child("curry_baseline")
    )
    assert asset_scope.archive("curry_native_archive").archive_path.startswith(
        "data/runtime/p1-curry-option-validation-native-2026-10-23/"
    )
    assert curry_history.archive("curry_native_archive").archive_path.startswith(
        "data/runtime/p1-tenki-placement-validation-native-2026-10-23/"
    )
    asset_archive = asset_scope.archive("curry_native_archive")
    history_archive = curry_history.archive("curry_native_archive")
    assert asset_archive == recovery._PinnedArchive(
        "curry_native_archive",
        "data/runtime/p1-curry-option-validation-native-2026-10-23/source-native.zip",
        "data/runtime/p1-curry-option-validation-native-2026-10-23/source-native-file-list.json",
        "d8b31b838f0b559adc513159a2e8135fd6ecaf2fab0c42897e3f8ebd6fc99582",
        "4c64d44dba562aa9f1ac8d133d63f56b9b0b6e4d02a826e144767477116cf04b",
        "29205c8ef0b98b07b3003a64baa6c7dede5e03391cf7e245b59905e0b2341028",
        494,
        recovery.EXPECTED_HEAD,
    )
    assert history_archive == recovery._PinnedArchive(
        "curry_native_archive",
        "data/runtime/p1-tenki-placement-validation-native-2026-10-23/source-native.zip",
        "data/runtime/p1-tenki-placement-validation-native-2026-10-23/source-native-file-list.json",
        "8c8c5d676d34ae03161491cd0a6dcedd5cc7c47d5ed2ecabdfbf4231c6e34e7e",
        "fd02e8e722a38b0edfdfc0058c9d4007f1059edfe3c641c8b4a2774a00939653",
        "e9538276391f0e08bfa707534aeab6c8e663784da8fcd9a97dc5ea0e9eb6e8f0",
        683,
        recovery.EXPECTED_HEAD,
    )
    assert asset_scope.dataset_count("historical_consumed") == 32
    assert asset_scope.dataset_count("historical_unknown") == 0
    assert curry_history.dataset_count("historical_consumed") == 32
    assert curry_history.dataset_count("historical_unknown") == 0
    assert asset_archive != history_archive


def test_production_source_tree_has_no_conflicting_hashes_for_same_file_path():
    sources = recovery._production_source_description()
    by_path: dict[str, set[str]] = {}

    def visit(node):
        for item in node.files:
            by_path.setdefault(item.relative_path, set()).add(item.sha256)
        for child in node.children:
            visit(child)

    visit(sources)
    conflicts = {path: hashes for path, hashes in by_path.items() if len(hashes) != 1}
    # The prior Curry scope explicitly records the codec file's before/after
    # hashes as a scoped source migration.  No other duplicated path may drift.
    baseline = (
        sources.child("asset_audit").child("historical_chain")
        .child("curry_baseline").child("validation_baseline")
        .child("runner_confirmation").child("placement_confirmation")
        .child("baseline")
    )
    codec_path = "crates/ygo-engine-adapter/src/codec.rs"
    # The duplicated file pins are from older frozen source trees and retain
    # that transition (224cb3 -> 68cf8d). The later Ground protection mapping
    # separately binds the current working-tree codec (e8f97e) as a semantic
    # value, so it must not rewrite these archived file-role pins.
    codec_transition_hashes = {
        "224cb3fa6a7700e871d79f202e0e3def4c3b394229bb57c462191f1da470a36e",
        "68cf8de986c331060f72d95a56acc68ecec34d916230f5302d33210b254ca42d",
    }
    assert conflicts == {codec_path: codec_transition_hashes}
