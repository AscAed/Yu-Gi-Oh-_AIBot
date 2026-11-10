"""Operation metadata structural and strict wire corpus; no engine calls."""
import copy
import json
import math
from pathlib import Path
import jsonschema
import pytest
ROOT = Path(__file__).resolve().parents[1]

def unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate")
        out[key] = value
    return out

def reject_constant(value):
    raise ValueError(value)

def validator(name):
    schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    checker = jsonschema.Draft202012Validator.TYPE_CHECKER.redefine("integer", lambda _, v: type(v) is int).redefine("number", lambda _, v: type(v) in (int, float) and math.isfinite(v))
    return jsonschema.validators.extend(jsonschema.Draft202012Validator, type_checker=checker)(schema)

def test_operation_schema_is_present_and_valid():
    validator("workbench-analysis-operation-v1.schema.json")
    validator("workbench-analysis-operation-revision-v1.schema.json")

def test_operation_shared_corpus():
    corpus = json.loads((ROOT / "tests/fixtures/workbench-analysis-operation-v1-cases.json").read_text(encoding="utf-8"))
    v = validator("workbench-analysis-operation-v1.schema.json")
    for case in corpus["cases"]:
        document = copy.deepcopy(corpus["golden"])
        for patch in case.get("patches", []):
            keys = patch["pointer"].strip("/").split("/")
            parent = document
            for key in keys[:-1]:
                parent = parent[key]
            if patch.get("remove"):
                del parent[keys[-1]]
            else:
                parent[keys[-1]] = patch["value"]
        text = json.dumps(document, separators=(",", ":"))
        for old, new in case.get("replace", []):
            assert old in text
            text = text.replace(old, new, 1)
        try:
            decoded = json.loads(text + case.get("suffix", ""), object_pairs_hook=unique, parse_constant=reject_constant)
            valid = v.is_valid(decoded)
        except (ValueError, TypeError):
            valid = False
        assert valid == case["schema_valid"], case["name"]


def test_revision_envelope_schema_rejects_missing_unknown_and_wrong_numbers():
    golden = json.loads((ROOT / "tests/fixtures/workbench-analysis-operation-v1-cases.json").read_text(encoding="utf-8"))["golden"]
    envelope = {"schema_version": 1, "kind": "workbench_analysis_operation_revision", "operation_id": golden["operation_id"], "revision": 1, "previous_sha256": None, "record_sha256": "d" * 64, "record": golden}
    v = validator("workbench-analysis-operation-revision-v1.schema.json")
    assert v.is_valid(envelope)
    for field in envelope:
        mutated = copy.deepcopy(envelope)
        del mutated[field]
        assert not v.is_valid(mutated), field
    for field, value in [("revision", 1.0), ("revision", True), ("operation_id", "../escape"), ("previous_sha256", "bad"), ("previous_sha256", "e" * 64), ("private_path", "C:/private")]:
        mutated = copy.deepcopy(envelope)
        mutated[field] = value
        assert not v.is_valid(mutated), field
