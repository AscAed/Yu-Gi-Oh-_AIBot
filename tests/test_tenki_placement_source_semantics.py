"""Source-description inputs remain separate from fixed production defaults."""
from pathlib import Path

from ygo_eval import tenki_placement_diagnostics as diagnostics


class _SyntheticSources:
    def __init__(self):
        self.semantics = {"placement_context": "a" * 64}
        self.files = {
            "data/runtime/placement/research/calls.jsonl": "b" * 64,
            "data/runtime/placement/research/summary.json": "c" * 64,
        }

    def semantic_sha256(self, role: str) -> str:
        return self.semantics[role]

    def file_sha256(self, relative_path: str) -> str:
        return self.files[relative_path]


def test_source_mode_resolves_context_and_result_pins_from_description():
    repo = Path("synthetic-repo")
    experiment = repo / "data/runtime/placement"
    sources = _SyntheticSources()

    assert diagnostics._placement_context_hash() == diagnostics.PLACEMENT_CONTEXT
    assert diagnostics._placement_context_hash(sources) == "a" * 64
    assert diagnostics._placement_result_hashes(repo, experiment) == {
        "ledger": diagnostics.PLACEMENT_LEDGER_SHA256,
        "summary": diagnostics.PLACEMENT_SUMMARY_SHA256,
    }
    assert diagnostics._placement_result_hashes(repo, experiment, sources) == {
        "ledger": "b" * 64,
        "summary": "c" * 64,
    }
