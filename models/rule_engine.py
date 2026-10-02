"""Explainable threshold-based rules over actual financial metrics."""

from dataclasses import dataclass
from math import isfinite


SAVINGS_LOW_THRESHOLD = 0.10
SAVINGS_HEALTHY_THRESHOLD = 0.20
DISCRETIONARY_THRESHOLD = 0.20
BURN_RATE_INCOME_THRESHOLD = 0.80
DEBT_INCOME_THRESHOLD = 0.20


@dataclass
class RuleThresholds:
	savings_low: float = SAVINGS_LOW_THRESHOLD
	savings_healthy: float = SAVINGS_HEALTHY_THRESHOLD
	discretionary: float = DISCRETIONARY_THRESHOLD
	burn_rate_income: float = BURN_RATE_INCOME_THRESHOLD
	debt_income: float = DEBT_INCOME_THRESHOLD

	def to_dict(self) -> dict[str, float]:
		return {
			"savings_low": self.savings_low,
			"savings_healthy": self.savings_healthy,
			"discretionary": self.discretionary,
			"burn_rate_income": self.burn_rate_income,
			"debt_income": self.debt_income,
		}

	@classmethod
	def from_dict(cls, data: dict | None) -> "RuleThresholds":
		if not data or not isinstance(data, dict):
			return cls()
		return cls(
			savings_low=float(data.get("savings_low", SAVINGS_LOW_THRESHOLD)),
			savings_healthy=float(data.get("savings_healthy", SAVINGS_HEALTHY_THRESHOLD)),
			discretionary=float(data.get("discretionary", DISCRETIONARY_THRESHOLD)),
			burn_rate_income=float(data.get("burn_rate_income", BURN_RATE_INCOME_THRESHOLD)),
			debt_income=float(data.get("debt_income", DEBT_INCOME_THRESHOLD)),
		)


@dataclass
class RuleResult:
	rule_id: str
	condition: str
	current_value: float | None
	threshold: float | None
	result: str
	recommendation: str
	priority: str
	details: str


def evaluate_financial_rules(
	metrics: dict,
	emergency_reserve_current: float,
	emergency_reserve_target: float,
	monthly_debt_payment: float,
	thresholds: RuleThresholds | None = None,
) -> list[RuleResult]:
	"""Evaluate each IF-THEN rule using monthly metrics, explicit user inputs, and configurable thresholds."""
	_validate_nonnegative("Current emergency reserve", emergency_reserve_current)
	_validate_nonnegative("Emergency reserve target", emergency_reserve_target)
	_validate_nonnegative("Monthly debt payment", monthly_debt_payment)

	if thresholds is None:
		thresholds = RuleThresholds()

	income = _finite_value(metrics.get("income"))
	savings_ratio = _finite_value(metrics.get("savings_ratio"))
	discretionary_ratio = _finite_value(metrics.get("discretionary_ratio"))
	burn_rate = _finite_value(metrics.get("monthly_burn_rate"))
	has_income = income is not None and income > 0

	return [
		_rule(
			"R01",
			f"Savings ratio < {thresholds.savings_low:.0%}",
			savings_ratio,
			thresholds.savings_low,
			savings_ratio is not None and savings_ratio < thresholds.savings_low,
			"Increase the portion of monthly income directed to savings.",
			"High",
			"Savings ratio = (monthly income - monthly expenses) / monthly income.",
			is_evaluable=savings_ratio is not None,
		),
		_rule(
			"R02",
			f"Discretionary ratio > {thresholds.discretionary:.0%}",
			discretionary_ratio,
			thresholds.discretionary,
			discretionary_ratio is not None and discretionary_ratio > thresholds.discretionary,
			"Review discretionary expenses and consider a lower monthly target.",
			"Medium",
			"Discretionary ratio = discretionary expenses / total expenses.",
			is_evaluable=discretionary_ratio is not None,
		),
		_rule(
			"R03",
			f"Monthly burn rate > {thresholds.burn_rate_income:.0%} of monthly income",
			burn_rate / income if has_income and burn_rate is not None else None,
			thresholds.burn_rate_income,
			has_income and burn_rate is not None and burn_rate / income > thresholds.burn_rate_income,
			"Investigate the recent spending pace; the 30-day burn estimate is high relative to income.",
			"High",
			"Current value is the 30-day trailing spending estimate divided by monthly income.",
			is_evaluable=has_income and burn_rate is not None,
		),
		_rule(
			"R04",
			"Current emergency reserve < configured target",
			float(emergency_reserve_current),
			float(emergency_reserve_target),
			emergency_reserve_current < emergency_reserve_target,
			"Increase the emergency reserve toward the target you entered.",
			"High" if emergency_reserve_current < emergency_reserve_target else "Low",
			"Reserve balance and target are user-entered because the transaction ledger does not identify savings accounts.",
		),
		_rule(
			"R05",
			f"Monthly debt payment > {thresholds.debt_income:.0%} of monthly income",
			monthly_debt_payment / income if has_income else None,
			thresholds.debt_income,
			has_income and monthly_debt_payment / income > thresholds.debt_income,
			"Review the debt payment burden against monthly income.",
			"High",
			"Debt payment is user-entered unless separately tracked in the transaction descriptions.",
			is_evaluable=has_income,
		),
		_rule(
			"R06",
			f"Savings ratio >= {thresholds.savings_healthy:.0%}",
			savings_ratio,
			thresholds.savings_healthy,
			savings_ratio is not None and savings_ratio >= thresholds.savings_healthy,
			"Maintain the current savings pattern while keeping other obligations funded.",
			"Positive",
			"This positive rule uses the same monthly savings ratio shown in the dashboard.",
			is_evaluable=savings_ratio is not None,
		),
	]


def _rule(
	rule_id: str,
	condition: str,
	current_value: float | None,
	threshold: float | None,
	triggered: bool,
	recommendation: str,
	priority: str,
	details: str,
	is_evaluable: bool = True,
) -> RuleResult:
	result = "Not evaluated" if not is_evaluable else "Triggered" if triggered else "Not triggered"
	return RuleResult(
		rule_id=rule_id,
		condition=condition,
		current_value=current_value,
		threshold=threshold,
		result=result,
		recommendation=recommendation,
		priority=priority,
		details=details,
	)


def _finite_value(value) -> float | None:
	if value is None:
		return None
	try:
		parsed = float(value)
	except (TypeError, ValueError):
		return None
	return parsed if isfinite(parsed) else None


def _validate_nonnegative(label: str, value: float) -> None:
	parsed = _finite_value(value)
	if parsed is None or parsed < 0:
		raise ValueError(f"{label} must be a finite, nonnegative amount.")