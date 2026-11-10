"""Offline structural checks for the local analysis HTTP wire contract."""
import copy
import pytest
from test_workbench_analysis_operation_schema import validator


def test_http_request_schema_accepts_only_explicit_contracts():
    check = validator("workbench-analysis-http-v1.schema.json")
    allocate = {"schema_version": 1, "kind": "analysis_operation_allocate"}
    cancel = {"schema_version": 1, "kind": "analysis_cancel", "expected_revision": 2}
    assert check.is_valid(allocate)
    assert check.is_valid(cancel)
    for original in (allocate, cancel):
        for key in original:
            broken = copy.deepcopy(original)
            del broken[key]
            assert not check.is_valid(broken)
        broken = dict(original, local_path="C:/private")
        assert not check.is_valid(broken)


@pytest.mark.parametrize("value", [True, 1.0, 0, -1, "2", None])
def test_http_revision_requires_positive_integer(value):
    check = validator("workbench-analysis-http-v1.schema.json")
    assert not check.is_valid({"schema_version": 1, "kind": "analysis_cancel", "expected_revision": value})
