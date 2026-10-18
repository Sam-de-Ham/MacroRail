import pytest

from macrorail.stack.plan import PlanError, estimate_seconds, move_time, plan_count, plan_range

LOW, HIGH = 200, 56000


def test_range_divisible_ends_exactly_on_end() -> None:
    plan = plan_range(1000, 1040, 4, LOW, HIGH)
    assert plan.positions == tuple(range(1000, 1041, 4))
    assert plan.count == 11


def test_range_not_divisible_adds_a_shot_past_the_end() -> None:
    plan = plan_range(1000, 1041, 4, LOW, HIGH)
    assert plan.count == 12
    assert plan.end == 1044 >= 1041


def test_range_can_run_toward_home() -> None:
    plan = plan_range(2000, 1990, 3, LOW, HIGH)
    assert plan.direction == -1
    assert plan.positions == (2000, 1997, 1994, 1991, 1988)


def test_count_mode() -> None:
    plan = plan_count(1000, 5, 4, -1, LOW, HIGH)
    assert plan.positions == (1000, 995, 990, 985)


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ((1000, 1000, 4), "same position"),
        ((1000, 1040, 0), "at least one"),
        ((55990, 56010, 4), "past the end"),
    ],
)
def test_range_errors(args: tuple[int, int, int], message: str) -> None:
    with pytest.raises(PlanError, match=message):
        plan_range(*args, LOW, HIGH)


def test_extra_shot_must_also_fit() -> None:
    with pytest.raises(PlanError, match="past the end"):
        plan_range(55901, 55999, 4, LOW, HIGH)  # the covering shot would land on 56001
    plan = plan_range(55900, 55996, 4, LOW, HIGH)
    assert plan.end == 55996


def test_move_time_short_move_is_triangular() -> None:
    assert move_time(20, 400, 4000) == pytest.approx(2 * (20 / 4000) ** 0.5)
    assert move_time(4000, 400, 4000) == pytest.approx(4000 / 400 + 400 / 4000)


def test_estimate() -> None:
    plan = plan_count(1000, 4, 10, 1, LOW, HIGH)
    per_move = move_time(4, 400, 4000)
    assert estimate_seconds(plan, 400, 4000, 0.5, 1.5) == pytest.approx(10 * 2.0 + 9 * per_move)
