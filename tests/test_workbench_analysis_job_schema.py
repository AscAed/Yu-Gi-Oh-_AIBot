"""Shared structural/lexical corpus; Rust additionally checks bindings."""

import copy
import json
import math
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_job_schema_is_present_and_valid():
    schema = json.loads((ROOT / "schemas/workbench-analysis-job-v1.schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)


def materialize(corpus, case):
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
    text = json.dumps(document, separators=(",", ":"), ensure_ascii=False)
    for replacement in case.get("replace", []):
        assert replacement[0] in text
        text = text.replace(*replacement, 1)
    return text + case.get("suffix", "")


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def test_job_shared_corpus():
    corpus = json.loads((ROOT / "tests/fixtures/workbench-analysis-job-v1-cases.json").read_text())
    schema = json.loads((ROOT / "schemas/workbench-analysis-job-v1.schema.json").read_text())
    # JSON Schema's mathematical integer includes 1.0; the wire contract
    # additionally requires lexical integers, as serde does for Rust u64.
    checker = jsonschema.Draft202012Validator.TYPE_CHECKER.redefine(
        "integer", lambda _checker, value: type(value) is int
    ).redefine("number", lambda _, v: type(v) in (int, float) and math.isfinite(v))
    validator = jsonschema.validators.extend(jsonschema.Draft202012Validator, type_checker=checker)(schema)
    for case in corpus["cases"]:
        text = materialize(corpus, case)
        try:
            document = json.loads(text, object_pairs_hook=unique, parse_constant=reject_constant)
            valid = validator.is_valid(document)
        except (ValueError, TypeError):
            valid = False
        assert valid == case["schema_valid"], case["name"]


def reject_constant(_value):
    raise ValueError("non-JSON numeric constant")


@pytest.mark.parametrize("number", [True, 1.0, -1, None])
def test_strict_wire_integer(number):
    schema = json.loads((ROOT / "schemas/workbench-analysis-job-v1.schema.json").read_text())
    corpus = json.loads((ROOT / "tests/fixtures/workbench-analysis-job-v1-cases.json").read_text())
    document = copy.deepcopy(corpus["golden"])
    document["revision"] = number
    checker = jsonschema.Draft202012Validator.TYPE_CHECKER.redefine("integer", lambda _, v: type(v) is int)
    validator = jsonschema.validators.extend(jsonschema.Draft202012Validator, type_checker=checker)(schema)
    assert not validator.is_valid(document)
