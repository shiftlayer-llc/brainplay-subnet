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
