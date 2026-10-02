"""A* search for low-disruption monthly savings plans."""

from dataclasses import dataclass, field
from datetime import date
from heapq import heappop, heappush
from itertools import count
from math import ceil, isfinite


MAX_EXPLORED_STATES = 50_000
MONTHLY_ACTION_FRACTIONS = (0.25, 0.5, 0.75, 1.0)


@dataclass
class GoalPlanResult:
	feasible: bool
	status: str
	goal_name: str
	target_amount: float
	initial_savings: float
	maximum_monthly_saving: float
	effective_monthly_limit: float
	initial_state: dict
	explored_states: list[dict] = field(default_factory=list)
	selected_path: list[dict] = field(default_factory=list)
	nodes_explored: int = 0
	path_length: int = 0
	final_cost: float | None = None
	goal_month: date | None = None
	explanation: str = ""


def plan_savings_goal(
	goal_name: str,
	target_amount: float,
	current_savings: float,
	maximum_monthly_saving: float,
	baseline_monthly_savings: float = 0.0,
	maximum_lifestyle_cut: float | None = None,
	start_month: date | None = None,
	max_explored_states: int = MAX_EXPLORED_STATES,
) -> GoalPlanResult:
	"""Search monthly contribution states with A* using f(n) = g(n) + h(n)."""
	_validate_amount("Target amount", target_amount, positive=True)
	_validate_amount("Current savings", current_savings)
	_validate_amount("Maximum monthly saving", maximum_monthly_saving, positive=True)
	_validate_amount("Baseline monthly savings", baseline_monthly_savings)
	if maximum_lifestyle_cut is not None:
		_validate_amount("Maximum lifestyle cut", maximum_lifestyle_cut)
	if not goal_name.strip():
		raise ValueError("Enter a goal name.")

	planning_month = (start_month or date.today()).replace(day=1)
	effective_limit = float(maximum_monthly_saving)
	if maximum_lifestyle_cut is not None:
		effective_limit = min(
			effective_limit,
			float(baseline_monthly_savings) + float(maximum_lifestyle_cut),
		)

	initial_state = {
		"month_index": 0,
		"month": planning_month,
		"savings": round(float(current_savings), 2),
		"remaining_target": max(0.0, float(target_amount) - float(current_savings)),
		"g": 0.0,
		"h": _heuristic(target_amount, current_savings, effective_limit),
		"f": _heuristic(target_amount, current_savings, effective_limit),
	}
	if current_savings >= target_amount:
		return GoalPlanResult(
			feasible=True,
			status="Goal already funded",
			goal_name=goal_name,
			target_amount=float(target_amount),
			initial_savings=float(current_savings),
			maximum_monthly_saving=float(maximum_monthly_saving),
			effective_monthly_limit=effective_limit,
			initial_state=initial_state,
			selected_path=[initial_state],
			goal_month=planning_month,
			explanation="Current savings already meet the target; no monthly contribution path is needed.",
		)

	if effective_limit <= 0:
		return _infeasible_result(
			goal_name,
			target_amount,
			current_savings,
			maximum_monthly_saving,
			effective_limit,
			initial_state,
			"The lifestyle restriction and monthly saving limit allow no positive contribution.",
		)

	action_values = {
		round(effective_limit * fraction, 2)
		for fraction in MONTHLY_ACTION_FRACTIONS
	}
	if baseline_monthly_savings > 0:
		action_values.add(round(min(baseline_monthly_savings, effective_limit), 2))
	actions = sorted(value for value in action_values if value > 0)
	if not actions:
		return _infeasible_result(
			goal_name,
			target_amount,
			current_savings,
			maximum_monthly_saving,
			effective_limit,
			initial_state,
			"No positive monthly saving action is available.",
		)

	initial_key = (0, round(current_savings * 100))
	open_set = []
	sequence = count()
	initial_h = _heuristic(target_amount, current_savings, effective_limit)
	heappush(open_set, (initial_h, initial_h, next(sequence), initial_key))
	best_cost = {initial_key: 0.0}
	parent: dict[tuple[int, int], tuple[tuple[int, int], float, float]] = {}
	explored: list[dict] = []
	goal_key = None

	while open_set and len(explored) < max_explored_states:
		_, _, _, state = heappop(open_set)
		month_index, savings_cents = state
		savings = savings_cents / 100
		g_score = best_cost[state]
		h_score = _heuristic(target_amount, savings, effective_limit)
		explored.append(
			{
				"month_index": month_index,
				"month": _add_months(planning_month, month_index),
				"savings": savings,
				"remaining_target": max(0.0, target_amount - savings),
				"g": g_score,
				"h": h_score,
				"f": g_score + h_score,
			}
		)
		if savings >= target_amount:
			goal_key = state
			break

		for proposed_saving in actions:
			contribution = min(proposed_saving, target_amount - savings)
			extra_lifestyle_cut = max(0.0, contribution - baseline_monthly_savings)
			disruption_denominator = max(
				maximum_lifestyle_cut if maximum_lifestyle_cut is not None else effective_limit,
				1.0,
			)
			disruption_penalty = extra_lifestyle_cut / disruption_denominator
			next_state = (month_index + 1, round((savings + contribution) * 100))
			next_cost = g_score + 1.0 + disruption_penalty
			if next_cost >= best_cost.get(next_state, float("inf")):
				continue

			best_cost[next_state] = next_cost
			parent[next_state] = (state, contribution, disruption_penalty)
			heuristic = _heuristic(target_amount, next_state[1] / 100, effective_limit)
			heappush(open_set, (next_cost + heuristic, heuristic, next(sequence), next_state))

	if goal_key is None:
		reason = (
			"The search-state limit was reached before a path was found."
			if open_set
			else "No feasible monthly contribution path reaches the target."
		)
		return _infeasible_result(
			goal_name,
			target_amount,
			current_savings,
			maximum_monthly_saving,
			effective_limit,
			initial_state,
			reason,
			explored_states=explored,
		)

	path = _reconstruct_path(
		goal_key,
		initial_key,
		parent,
		best_cost,
		target_amount,
		planning_month,
		effective_limit,
	)
	goal_month = path[-1]["month"]
	return GoalPlanResult(
		feasible=True,
		status="Feasible path found",
		goal_name=goal_name,
		target_amount=float(target_amount),
		initial_savings=float(current_savings),
		maximum_monthly_saving=float(maximum_monthly_saving),
		effective_monthly_limit=effective_limit,
		initial_state=initial_state,
		explored_states=explored,
		selected_path=path,
		nodes_explored=len(explored),
		path_length=len(path) - 1,
		final_cost=best_cost[goal_key],
		goal_month=goal_month,
		explanation=(
			"A* selected the lowest-cost path found. Each month costs 1; saving above the observed "
			"baseline adds a normalized lifestyle-disruption penalty. The heuristic is the ceiling "
			"of remaining target divided by the maximum permitted monthly contribution."
		),
	)


def _heuristic(target_amount: float, savings: float, maximum_contribution: float) -> int:
	remaining = max(0.0, target_amount - savings)
	if remaining == 0:
		return 0
	if maximum_contribution <= 0:
		return 0
	return ceil(remaining / maximum_contribution)


def _reconstruct_path(
	goal_key: tuple[int, int],
	initial_key: tuple[int, int],
	parent: dict[tuple[int, int], tuple[tuple[int, int], float, float]],
	best_cost: dict[tuple[int, int], float],
	target_amount: float,
	start_month: date,
	maximum_contribution: float,
) -> list[dict]:
	states = []
	current = goal_key
	while current != initial_key:
		previous, contribution, disruption = parent[current]
		states.append((current, contribution, disruption))
		current = previous
	states.reverse()

	path = [
		{
			**{
				"month_index": 0,
				"month": start_month,
				"savings": initial_key[1] / 100,
				"remaining_target": max(0.0, target_amount - initial_key[1] / 100),
				"monthly_saving": 0.0,
				"disruption_penalty": 0.0,
			},
			"g": 0.0,
			"h": _heuristic(target_amount, initial_key[1] / 100, maximum_contribution),
			"f": _heuristic(target_amount, initial_key[1] / 100, maximum_contribution),
		}
	]
	for state, contribution, disruption in states:
		month_index, savings_cents = state
		savings = savings_cents / 100
		g_score = best_cost[state]
		h_score = _heuristic(target_amount, savings, maximum_contribution)
		path.append(
			{
				"month_index": month_index,
				"month": _add_months(start_month, month_index),
				"savings": savings,
				"remaining_target": max(0.0, target_amount - savings),
				"monthly_saving": contribution,
				"disruption_penalty": disruption,
				"g": g_score,
				"h": h_score,
				"f": g_score + h_score,
			}
		)
	return path


def _add_months(month: date, count_months: int) -> date:
	zero_based = month.year * 12 + month.month - 1 + count_months
	year, month_index = divmod(zero_based, 12)
	return date(year, month_index + 1, 1)


def _infeasible_result(
	goal_name: str,
	target_amount: float,
	current_savings: float,
	maximum_monthly_saving: float,
	effective_limit: float,
	initial_state: dict,
	explanation: str,
	explored_states: list[dict] | None = None,
) -> GoalPlanResult:
	explored = explored_states or []
	return GoalPlanResult(
		feasible=False,
		status="Search limit reached" if "state limit" in explanation else "No feasible path",
		goal_name=goal_name,
		target_amount=float(target_amount),
		initial_savings=float(current_savings),
		maximum_monthly_saving=float(maximum_monthly_saving),
		effective_monthly_limit=effective_limit,
		initial_state=initial_state,
		explored_states=explored,
		nodes_explored=len(explored),
		explanation=explanation,
	)


def _validate_amount(label: str, value: float, positive: bool = False) -> None:
	try:
		amount = float(value)
	except (TypeError, ValueError) as error:
		raise ValueError(f"{label} must be a numeric amount.") from error
	if not isfinite(amount) or amount < 0 or (positive and amount <= 0):
		condition = "greater than zero" if positive else "finite and nonnegative"
		raise ValueError(f"{label} must be {condition}.")
