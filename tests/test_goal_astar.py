"""Unit tests for the A* savings goal planner."""

from datetime import date
import pytest
from models.goal_astar import (
    GoalPlanResult,
    _heuristic,
    plan_savings_goal,
)


def test_heuristic_admissibility():
    """Verify that the ceiling heuristic produces an exact lower bound on months."""
    assert _heuristic(1000.0, 0.0, 200.0) == 5
    assert _heuristic(1000.0, 100.0, 200.0) == 5
    assert _heuristic(1000.0, 850.0, 200.0) == 1
    assert _heuristic(1000.0, 1000.0, 200.0) == 0
    assert _heuristic(1000.0, 1200.0, 200.0) == 0
    assert _heuristic(1000.0, 0.0, 0.0) == 0


def test_feasible_goal_plan_path():
    """Test finding an optimal A* path to reach a savings goal."""
    result = plan_savings_goal(
        goal_name="Emergency Buffer",
        target_amount=1200.0,
        current_savings=200.0,
        maximum_monthly_saving=250.0,
        baseline_monthly_savings=150.0,
        start_month=date(2026, 1, 1),
    )

    assert isinstance(result, GoalPlanResult)
    assert result.feasible is True
    assert result.status == "Feasible path found"
    assert result.path_length > 0
    assert len(result.selected_path) == result.path_length + 1
    # Check that initial state has current savings
    assert result.selected_path[0]["savings"] == 200.0
    # Final state savings must meet or exceed target amount
    assert result.selected_path[-1]["savings"] >= 1200.0
    # Month progression
    assert result.goal_month is not None
    assert result.goal_month > date(2026, 1, 1)
    # Search stats
    assert result.nodes_explored > 0


def test_goal_already_funded():
    """When current savings >= target, goal is immediately achieved."""
    result = plan_savings_goal(
        goal_name="Vacation Fund",
        target_amount=500.0,
        current_savings=550.0,
        maximum_monthly_saving=100.0,
        start_month=date(2026, 3, 1),
    )

    assert result.feasible is True
    assert result.status == "Goal already funded"
    assert result.path_length == 0
    assert len(result.selected_path) == 1
    assert result.goal_month == date(2026, 3, 1)


def test_lifestyle_restriction_caps_contribution():
    """Effective limit is capped by baseline + max lifestyle cut."""
    result = plan_savings_goal(
        goal_name="New Laptop",
        target_amount=1000.0,
        current_savings=0.0,
        maximum_monthly_saving=500.0,
        baseline_monthly_savings=100.0,
        maximum_lifestyle_cut=50.0,  # Caps monthly contribution at 150.0
        start_month=date(2026, 1, 1),
    )

    assert result.feasible is True
    assert result.effective_monthly_limit == 150.0
    # Every monthly contribution in path must not exceed effective limit
    for step in result.selected_path[1:]:
        assert step["monthly_saving"] <= 150.0 + 1e-9


def test_zero_effective_limit_is_infeasible():
    """When effective monthly limit is zero, planner returns clean infeasible result."""
    result = plan_savings_goal(
        goal_name="House Downpayment",
        target_amount=50000.0,
        current_savings=1000.0,
        maximum_monthly_saving=500.0,
        baseline_monthly_savings=0.0,
        maximum_lifestyle_cut=0.0,  # Capped at 0 + 0 = 0
    )

    assert result.feasible is False
    assert result.status == "No feasible path"
    assert "allow no positive contribution" in result.explanation.lower()


def test_max_state_limit_fallback():
    """Very small search node limit returns a clean fallback result without unhandled exception."""
    result = plan_savings_goal(
        goal_name="Car",
        target_amount=10000.0,
        current_savings=0.0,
        maximum_monthly_saving=50.0,
        max_explored_states=3,
    )

    assert result.feasible is False
    assert result.status == "Search limit reached"
    assert result.nodes_explored <= 4


def test_invalid_arguments_raise_value_errors():
    """Target and max monthly saving must be positive; savings cannot be negative."""
    with pytest.raises(ValueError, match="Target amount must be greater than zero."):
        plan_savings_goal("Test", 0.0, 0.0, 100.0)

    with pytest.raises(ValueError, match="Maximum monthly saving must be greater than zero."):
        plan_savings_goal("Test", 500.0, 0.0, -10.0)

    with pytest.raises(ValueError, match="Current savings must be finite and nonnegative."):
        plan_savings_goal("Test", 500.0, -50.0, 100.0)

    with pytest.raises(ValueError, match="Enter a goal name."):
        plan_savings_goal("   ", 500.0, 0.0, 100.0)
