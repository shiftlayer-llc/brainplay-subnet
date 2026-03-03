"""TwentyQ scoring helper placeholder (exact implementation later)."""


def score_twentyq_attempt(*, solved: bool, question_index: int) -> float:
    if not solved:
        return 0.0
    if question_index <= 0:
        return 0.0
    if question_index <= 20:
        return 1.0
    if question_index > 25:
        return 0.0
    bonus_used = question_index - 20
    return max(0.0, 1.0 - 0.1 * bonus_used)
