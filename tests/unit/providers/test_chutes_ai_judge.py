import asyncio

from game.providers.judge.chutes_ai import ChutesAIJudge


def test_chutes_ai_normalize_answer():
    assert ChutesAIJudge.normalize_answer("Yes") == "yes"
    assert ChutesAIJudge.normalize_answer(" NO ") == "no"
    assert ChutesAIJudge.normalize_answer("unknown.") == "unknown"
    assert ChutesAIJudge.normalize_answer("Answer: no") == "no"
    assert ChutesAIJudge.normalize_answer("The answer is yes.") == "yes"
    assert ChutesAIJudge.normalize_answer('{"answer":"yes"}') == "yes"
    assert (
        ChutesAIJudge.normalize_answer(
            '```json\n{"reasoning":"it is alive","answer":"yes"}\n```'
        )
        == "yes"
    )
    assert ChutesAIJudge.normalize_answer("maybe") == "unknown"


def test_chutes_ai_fallback_heuristic_answer():
    judge = ChutesAIJudge(api_key="", base_url="")
    answer = asyncio.run(judge.answer(secret="apple", question="Is it apple?"))
    assert answer == "yes"
    answer = asyncio.run(judge.answer(secret="apple", question="Is it banana?"))
    assert answer in {"no", "unknown"}


def test_chutes_ai_uses_dataset_properties_in_fallback():
    judge = ChutesAIJudge(api_key="", base_url="")
    answer = asyncio.run(
        judge.answer(
            secret="giraffe",
            question="Is it an animal?",
            properties={"animal": "True", "has_wheels": "False"},
        )
    )
    assert answer == "yes"

    answer = asyncio.run(
        judge.answer(
            secret="giraffe",
            question="Does it have wheels?",
            properties={"animal": "True", "has_wheels": "False"},
        )
    )
    assert answer == "no"


def test_chutes_ai_tries_alternative_model_before_heuristic(monkeypatch):
    calls = []

    class _Message:
        def __init__(self, content):
            self.content = content
            self.reasoning_content = ""
            self.reasoning = ""

    class _Choice:
        def __init__(self, content):
            self.finish_reason = "stop"
            self.message = _Message(content)

    class _Result:
        def __init__(self, content):
            self.choices = [_Choice(content)]

    class _Completions:
        def create(self, **kwargs):
            model = kwargs["model"]
            calls.append(model)
            if model == "openai/gpt-oss-120b-TEE":
                raise RuntimeError("Error code: 429")
            if model == "openai/gpt-oss-20b-TEE":
                return _Result('{"answer":"yes","reasoning":"fallback model worked"}')
            raise AssertionError(f"unexpected model {model}")

    class _Chat:
        def __init__(self):
            self.completions = _Completions()

    class _FakeOpenAI:
        def __init__(self, *args, **kwargs):
            self.chat = _Chat()

    monkeypatch.setattr("game.providers.judge.chutes_ai.OpenAI", _FakeOpenAI)

    judge = ChutesAIJudge(
        api_key="test-key",
        base_url="https://llm.chutes.ai/v1",
        model="openai/gpt-oss-120b-TEE",
    )
    answer = asyncio.run(judge.answer(secret="apple", question="Is it a fruit?"))

    assert calls == ["openai/gpt-oss-120b-TEE", "openai/gpt-oss-20b-TEE"]
    assert answer == "yes"
