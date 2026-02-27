from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_twentyq_scoring_module():
    file_path = (
        Path(__file__).resolve().parents[4]
        / "game"
        / "plugins"
        / "twentyq"
        / "scoring.py"
    )
    spec = spec_from_file_location("twentyq_scoring_module", file_path)
    module = module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_twentyq_scoring_placeholder_rules():
    mod = _load_twentyq_scoring_module()
    assert mod.score_twentyq_attempt(solved=True, question_index=20) == 1.0
    assert mod.score_twentyq_attempt(solved=True, question_index=21) == 0.9
    assert mod.score_twentyq_attempt(solved=True, question_index=25) == 0.5
    assert mod.score_twentyq_attempt(solved=False, question_index=25) == 0.0
