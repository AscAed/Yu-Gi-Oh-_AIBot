from __future__ import annotations

import hashlib

import pytest

from ygo_eval import native_tenki_placement as transition


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class _SyntheticTransitionSources:
    def __init__(self, *, worker_old: str, worker: str, codec_old: str, codec: str):
        self._values = {
            "transition_old_worker_sha256": worker_old,
            "transition_new_worker_sha256": worker,
            "curry_scope_codec_old_sha256": codec_old,
            "curry_scope_codec_sha256": codec,
        }

    def semantic_sha256(self, role: str) -> str:
        try:
            return self._values[role]
        except KeyError:
            raise KeyError(role) from None


def _synthetic_transition(worker_hash: str, worker_old_hash: str) -> dict:
    return transition._seal_transition({
        "schema_version": 2,
        "scope": transition.SCOPE,
        "migration": {
            "path": transition.TRANSITION_RELATIVE_PATH.as_posix(),
            "old_sha256": worker_old_hash,
            "observed_sha256": worker_hash,
        },
    })


def test_source_mode_uses_test_description_hashes_but_default_keeps_fixed_production_hashes():
    worker_old = _sha(b"old synthetic worker")
    worker = _sha(b"independent synthetic worker")
    codec_old = _sha(b"old synthetic codec")
    codec = _sha(b"independent synthetic codec")
    sources = _SyntheticTransitionSources(
        worker_old=worker_old, worker=worker, codec_old=codec_old, codec=codec,
    )
    worker_path = transition.TRANSITION_RELATIVE_PATH.as_posix()
    codec_path = transition.CURRY_SCOPE_PROTECTED_SOURCE_CHANGE["path"]
    protected = {
        worker_path: worker_old,
        codec_path: codec_old,
    }
    actual = {worker_path: worker, codec_path: codec}
    sealed = _synthetic_transition(worker, worker_old)

    assert transition._transition_target_hash(2) == transition.TRANSITION_V2_NEW_SHA256
    assert transition._transition_target_hash(2, _sources=sources) == worker
    assert transition._validate_worker_transition(
        protected, actual, sealed, sealed, _sources=sources,
    ) == worker
    assert transition._effective_protected_map(
        protected, actual, sealed, sealed,
        protection_scope=transition.CURRY_SCOPE_PROTECTED_SOURCE_CHANGE["scope"],
        _sources=sources,
    ) == actual


def test_source_mode_rejects_worker_or_codec_bytes_that_disagree_with_fixed_description():
    worker_old = _sha(b"old synthetic worker")
    worker = _sha(b"independent synthetic worker")
    codec_old = _sha(b"old synthetic codec")
    codec = _sha(b"independent synthetic codec")
    sources = _SyntheticTransitionSources(
        worker_old=worker_old, worker=worker, codec_old=codec_old, codec=codec,
    )
    worker_path = transition.TRANSITION_RELATIVE_PATH.as_posix()
    codec_path = transition.CURRY_SCOPE_PROTECTED_SOURCE_CHANGE["path"]
    protected = {
        worker_path: worker_old,
        codec_path: codec_old,
    }
    actual = {worker_path: _sha(b"other worker"), codec_path: codec}
    sealed = _synthetic_transition(worker, worker_old)

    with pytest.raises(ValueError, match="baseline_transition_input_mismatch|historical_protected_input_changed"):
        transition._validate_worker_transition(
            protected, actual, sealed, sealed, _sources=sources,
        )

    actual[worker_path] = worker
    actual[codec_path] = _sha(b"other codec")
    with pytest.raises(ValueError, match="protected_source_change_hash_mismatch"):
        transition._effective_protected_map(
            protected, actual, sealed, sealed,
            protection_scope=transition.CURRY_SCOPE_PROTECTED_SOURCE_CHANGE["scope"],
            _sources=sources,
        )
