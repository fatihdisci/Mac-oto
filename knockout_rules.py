from __future__ import annotations

import random
from typing import Any


def resolve_single_leg_knockout(
    *,
    match_id: str,
    team_a_key: str,
    team_b_key: str,
    regular_score_a: int,
    regular_score_b: int,
    game_index: int = 0,
) -> dict[str, Any]:
    score_a = int(regular_score_a)
    score_b = int(regular_score_b)
    if score_a < 0 or score_b < 0:
        raise ValueError("Scores must be non-negative.")

    if score_a != score_b:
        return {
            "score_a": score_a,
            "score_b": score_b,
            "decided_by": "normal_time",
            "regular_time_score_a": score_a,
            "regular_time_score_b": score_b,
            "extra_time_score_a": None,
            "extra_time_score_b": None,
            "penalty_score_a": None,
            "penalty_score_b": None,
            "penalty_kicks": [],
        }

    seed_key = (
        f"{match_id}:{team_a_key}:{team_b_key}:{score_a}:{score_b}:{int(game_index)}"
    )
    rng = random.Random(seed_key)

    et_a = rng.choices([0, 1, 2], weights=[0.63, 0.30, 0.07], k=1)[0]
    et_b = rng.choices([0, 1, 2], weights=[0.63, 0.30, 0.07], k=1)[0]
    total_a = score_a + int(et_a)
    total_b = score_b + int(et_b)
    if total_a != total_b:
        return {
            "score_a": int(total_a),
            "score_b": int(total_b),
            "decided_by": "extra_time",
            "regular_time_score_a": score_a,
            "regular_time_score_b": score_b,
            "extra_time_score_a": int(et_a),
            "extra_time_score_b": int(et_b),
            "penalty_score_a": None,
            "penalty_score_b": None,
            "penalty_kicks": [],
        }

    pen_a = 0
    pen_b = 0
    penalty_kicks: list[dict[str, Any]] = []
    for i in range(5):
        a_goal = rng.random() < 0.74
        b_goal = rng.random() < 0.74
        pen_a += int(a_goal)
        pen_b += int(b_goal)
        penalty_kicks.append({"team": "A", "round": i + 1, "scored": bool(a_goal)})
        penalty_kicks.append({"team": "B", "round": i + 1, "scored": bool(b_goal)})
        rem = 4 - i
        if pen_a > pen_b + rem:
            break
        if pen_b > pen_a + rem:
            break

    sudden_rounds = 0
    while pen_a == pen_b and sudden_rounds < 12:
        a_goal = rng.random() < 0.74
        b_goal = rng.random() < 0.74
        pen_a += int(a_goal)
        pen_b += int(b_goal)
        sudden_rounds += 1
        sudden_label = f"SD{sudden_rounds}"
        penalty_kicks.append({"team": "A", "round": sudden_label, "scored": bool(a_goal)})
        penalty_kicks.append({"team": "B", "round": sudden_label, "scored": bool(b_goal)})

    if pen_a == pen_b:
        if rng.random() < 0.5:
            pen_a += 1
            penalty_kicks.append({"team": "A", "round": "SDX", "scored": True})
            penalty_kicks.append({"team": "B", "round": "SDX", "scored": False})
        else:
            pen_b += 1
            penalty_kicks.append({"team": "A", "round": "SDX", "scored": False})
            penalty_kicks.append({"team": "B", "round": "SDX", "scored": True})

    if pen_a > pen_b:
        resolved_a = total_a + 1
        resolved_b = total_b
    else:
        resolved_a = total_a
        resolved_b = total_b + 1

    return {
        "score_a": int(resolved_a),
        "score_b": int(resolved_b),
        "decided_by": "penalties",
        "regular_time_score_a": score_a,
        "regular_time_score_b": score_b,
        "extra_time_score_a": int(et_a),
        "extra_time_score_b": int(et_b),
        "penalty_score_a": int(pen_a),
        "penalty_score_b": int(pen_b),
        "penalty_kicks": penalty_kicks,
    }
