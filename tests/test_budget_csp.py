"""Unit tests for the Constraint Satisfaction Problem (CSP) budget optimizer."""

import pytest
from models.budget_csp import (
    ALLOCATION_TARGETS,
    FIXED_ALLOCATIONS,
    BudgetOptimizationResult,
    optimize_budget_csp,
)


@pytest.fixture
def standard_targets():
    return {
        "housing": 1200.0,
        "debt_payment": 300.0,
        "food": 600.0,
        "transportation": 250.0,
        "health": 150.0,
        "education": 100.0,
        "emergency_reserve": 200.0,
        "discretionary": 400.0,
        "savings": 500.0,
    }


def test_feasible_optimal_budget(standard_targets):
    """Test that a well-funded income finds an optimal, feasible allocation."""
    income = 4000.0
    result = optimize_budget_csp(income, standard_targets)

    assert isinstance(result, BudgetOptimizationResult)
    assert result.feasible is True
    assert result.optimal is True
    assert "Feasible" in result.status
    assert result.total_allocation <= income + 1e-9
    assert result.allocations["housing"] == standard_targets["housing"]
    assert result.allocations["debt_payment"] == standard_targets["debt_payment"]
    assert result.statistics.nodes_explored > 0
    assert result.statistics.feasible_solutions >= 1
    assert result.objective_score is not None


def test_hard_constraints_housing_and_debt_preserved(standard_targets):
    """Housing and debt payment must be fully allocated at their hard minimums."""
    income = 2500.0  # Tighter income
    result = optimize_budget_csp(income, standard_targets)

    assert result.feasible is True
    assert result.allocations["housing"] == standard_targets["housing"]
    assert result.allocations["debt_payment"] == standard_targets["debt_payment"]
    assert result.constraints["Housing minimum is satisfied"] is True
    assert result.constraints["Minimum debt payment is satisfied"] is True
    assert result.constraints["Total allocation does not exceed monthly income"] is True


def test_mandatory_exceeds_income_is_infeasible(standard_targets):
    """When housing + debt exceeds income, search immediately fails with Infeasible."""
    income = 1400.0  # Less than housing (1200) + debt (300) = 1500
    result = optimize_budget_csp(income, standard_targets)

    assert result.feasible is False
    assert result.status == "Infeasible"
    assert result.allocations == {}
    assert "Hard minimums exceed the available monthly income." in result.resolution_note
    assert result.statistics.nodes_explored == 0


def test_zero_discretionary_budget(standard_targets):
    """When discretionary target is 0, allocation handles it gracefully without division by zero."""
    standard_targets["discretionary"] = 0.0
    income = 3500.0
    result = optimize_budget_csp(income, standard_targets)

    assert result.feasible is True
    assert result.allocations["discretionary"] == 0.0


def test_discretionary_penalty_above_cap(standard_targets):
    """Discretionary target exceeding 20% of income is capped or penalized in utility."""
    income = 2000.0  # 20% cap is 400
    standard_targets["discretionary"] = 800.0  # Requests 40%
    result = optimize_budget_csp(income, standard_targets)

    assert result.feasible is True
    assert result.discretionary_cap == 400.0
    # In tight income, discretionary allocation should not blow past the cap
    assert result.total_allocation <= income + 1e-9


def test_search_node_limit_triggers_gracefully(standard_targets):
    """When node limit is set very low, solver returns best solution found or cleanly reports limit."""
    income = 4000.0
    result = optimize_budget_csp(income, standard_targets, max_search_nodes=2)

    assert result.statistics.nodes_explored <= 3
    if not result.feasible:
        assert "Search limit reached" in result.status or result.status == "Infeasible"


def test_forward_checking_and_bound_pruning(standard_targets):
    """Verify statistics reflect forward checking and branch-and-bound prunes."""
    income = 3000.0
    result = optimize_budget_csp(income, standard_targets)

    assert result.statistics.forward_check_prunes > 0
    assert result.statistics.bound_prunes > 0


def test_invalid_income_raises_value_error(standard_targets):
    """Negative or infinite income must raise ValueError."""
    with pytest.raises(ValueError, match="Monthly income must be a finite, nonnegative amount."):
        optimize_budget_csp(-100.0, standard_targets)

    with pytest.raises(ValueError, match="Monthly income must be a finite, nonnegative amount."):
        optimize_budget_csp(float("nan"), standard_targets)


def test_missing_target_key_raises_value_error(standard_targets):
    """Missing any required target must raise ValueError."""
    del standard_targets["food"]
    with pytest.raises(ValueError, match="Missing allocation targets"):
        optimize_budget_csp(3000.0, standard_targets)


def test_negative_target_raises_value_error(standard_targets):
    """Negative target amount must raise ValueError."""
    standard_targets["food"] = -50.0
    with pytest.raises(ValueError, match="Food must be a finite, nonnegative amount."):
        optimize_budget_csp(3000.0, standard_targets)
