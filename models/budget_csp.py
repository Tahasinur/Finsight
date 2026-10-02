"""Constraint satisfaction solver for monthly budget allocations."""

from dataclasses import dataclass, field
from math import isfinite


ALLOCATION_TARGETS = [
	"food",
	"transportation",
	"health",
	"education",
	"emergency_reserve",
	"discretionary",
	"savings",
]
FIXED_ALLOCATIONS = ["housing", "debt_payment"]
DOMAIN_FRACTIONS = (0.0, 0.25, 0.5, 0.75, 1.0)
PREFERENCE_WEIGHTS = {
	"food": 2.5,
	"transportation": 2.0,
	"health": 2.7,
	"education": 1.6,
	"emergency_reserve": 4.0,
	"discretionary": 1.0,
	"savings": 3.5,
}
MAX_SEARCH_NODES = 200_000


@dataclass
class SearchStatistics:
	nodes_explored: int = 0
	forward_check_prunes: int = 0
	bound_prunes: int = 0
	backtracks: int = 0
	feasible_solutions: int = 0


@dataclass
class BudgetOptimizationResult:
	feasible: bool
	optimal: bool
	status: str
	allocations: dict[str, float]
	total_allocation: float
	remaining_amount: float
	discretionary_cap: float
	objective_score: float | None
	constraints: dict[str, bool]
	requested_targets: dict[str, float]
	statistics: SearchStatistics = field(default_factory=SearchStatistics)
	resolution_note: str = ""
	explanation: str = ""


def optimize_budget_csp(
	monthly_income: float,
	requested_targets: dict[str, float],
	max_search_nodes: int = MAX_SEARCH_NODES,
) -> BudgetOptimizationResult:
	"""Search for feasible allocations using backtracking, forward checking, and MRV."""
	_validate_inputs(monthly_income, requested_targets)
	income = float(monthly_income)
	targets = {name: float(value) for name, value in requested_targets.items()}
	mandatory_total = targets["housing"] + targets["debt_payment"]
	discretionary_cap = income * 0.20

	if mandatory_total > income:
		constraints = {
			"Total allocation does not exceed monthly income": False,
			"Housing minimum is satisfied": True,
			"Minimum debt payment is satisfied": True,
		}
		return BudgetOptimizationResult(
			feasible=False,
			optimal=True,
			status="Infeasible",
			allocations={},
			total_allocation=0.0,
			remaining_amount=income,
			discretionary_cap=discretionary_cap,
			objective_score=None,
			constraints=constraints,
			requested_targets=targets,
			resolution_note="Hard minimums exceed the available monthly income.",
			explanation=(
				f"Housing ({targets['housing']:,.2f}) plus required debt payment "
				f"({targets['debt_payment']:,.2f}) is greater than monthly income ({income:,.2f})."
			),
		)

	domains = {
		"housing": [targets["housing"]],
		"debt_payment": [targets["debt_payment"]],
	}
	for variable in ALLOCATION_TARGETS:
		target = targets[variable]
		values = {round(target * fraction, 2) for fraction in DOMAIN_FRACTIONS}
		domains[variable] = sorted(values, reverse=True)

	variables = FIXED_ALLOCATIONS + ALLOCATION_TARGETS
	statistics = SearchStatistics()
	best_allocations: dict[str, float] | None = None
	best_score = float("-inf")
	stopped_at_node_limit = False

	def utility(variable: str, amount: float) -> float:
		target = targets.get(variable, 0.0)
		if variable in FIXED_ALLOCATIONS or target <= 0:
			return 0.0
		score = PREFERENCE_WEIGHTS[variable] * amount / target
		if variable == "discretionary" and amount > discretionary_cap:
			score -= 1.5 * (amount - discretionary_cap) / max(target, 1.0)
		return score

	def search(assignments: dict[str, float], total: float, score: float) -> None:
		nonlocal best_allocations, best_score, stopped_at_node_limit
		if statistics.nodes_explored >= max_search_nodes:
			stopped_at_node_limit = True
			return
		statistics.nodes_explored += 1

		unassigned = [variable for variable in variables if variable not in assignments]
		if not unassigned:
			statistics.feasible_solutions += 1
			if score > best_score:
				best_score = score
				best_allocations = assignments.copy()
			return

		remaining_income = income - total
		live_domains: dict[str, list[float]] = {}
		for variable in unassigned:
			candidates = [amount for amount in domains[variable] if amount <= remaining_income + 1e-9]
			if len(candidates) != len(domains[variable]):
				statistics.forward_check_prunes += len(domains[variable]) - len(candidates)
			if not candidates:
				statistics.forward_check_prunes += 1
				statistics.backtracks += 1
				return
			live_domains[variable] = candidates

		if total + sum(min(values) for values in live_domains.values()) > income + 1e-9:
			statistics.forward_check_prunes += 1
			statistics.backtracks += 1
			return

		score_upper_bound = score + sum(
			max(utility(variable, amount) for amount in live_domains[variable])
			for variable in unassigned
		)
		if score_upper_bound <= best_score:
			statistics.bound_prunes += 1
			return

		variable = min(
			unassigned,
			key=lambda name: (len(live_domains[name]), -PREFERENCE_WEIGHTS.get(name, float("inf"))),
		)
		candidates = sorted(
			live_domains[variable],
			key=lambda amount: utility(variable, amount),
			reverse=True,
		)
		for amount in candidates:
			assignments[variable] = amount
			search(assignments, total + amount, score + utility(variable, amount))
			del assignments[variable]
			if stopped_at_node_limit:
				break

	search({}, 0.0, 0.0)
	if best_allocations is None:
		return BudgetOptimizationResult(
			feasible=False,
			optimal=not stopped_at_node_limit,
			status="Search limit reached without a feasible allocation" if stopped_at_node_limit else "Infeasible",
			allocations={},
			total_allocation=0.0,
			remaining_amount=income,
			discretionary_cap=discretionary_cap,
			objective_score=None,
			constraints={
				"Total allocation does not exceed monthly income": False,
				"Housing minimum is satisfied": False,
				"Minimum debt payment is satisfied": False,
			},
			requested_targets=targets,
			statistics=statistics,
			resolution_note="Flexible targets were searched at 0%, 25%, 50%, 75%, and 100% of each requested target.",
			explanation="No feasible assignment was found within the search limits.",
		)

	total_allocation = sum(best_allocations.values())
	constraints = {
		"Total allocation does not exceed monthly income": total_allocation <= income + 1e-9,
		"Housing minimum is satisfied": best_allocations["housing"] >= targets["housing"],
		"Minimum debt payment is satisfied": best_allocations["debt_payment"] >= targets["debt_payment"],
	}
	remaining_amount = max(0.0, income - total_allocation)
	status = "Feasible · optimal" if not stopped_at_node_limit else "Feasible · best found before search limit"
	return BudgetOptimizationResult(
		feasible=all(constraints.values()),
		optimal=not stopped_at_node_limit,
		status=status,
		allocations=best_allocations,
		total_allocation=total_allocation,
		remaining_amount=remaining_amount,
		discretionary_cap=discretionary_cap,
		objective_score=best_score,
		constraints=constraints,
		requested_targets=targets,
		statistics=statistics,
		resolution_note="Flexible targets were searched at 0%, 25%, 50%, 75%, and 100% of each requested target.",
		explanation=(
			"Recursive search held housing and debt at their hard minimums. It ranked feasible allocations "
			"with the declared weighted preference score, prioritizing emergency reserve and savings; "
			"discretionary spending above 20% of monthly income was penalized when feasible."
		),
	)


def _validate_inputs(monthly_income: float, requested_targets: dict[str, float]) -> None:
	if not isfinite(float(monthly_income)) or monthly_income < 0:
		raise ValueError("Monthly income must be a finite, nonnegative amount.")
	missing = set(FIXED_ALLOCATIONS + ALLOCATION_TARGETS).difference(requested_targets)
	if missing:
		raise ValueError(f"Missing allocation targets: {', '.join(sorted(missing))}")
	for name, value in requested_targets.items():
		if not isfinite(float(value)) or value < 0:
			raise ValueError(f"{name.replace('_', ' ').title()} must be a finite, nonnegative amount.")
