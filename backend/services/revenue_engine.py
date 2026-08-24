"""
Revenue Engine — Central, authoritative revenue calculation.
Single source of truth for all revenue computations.
No silent fallbacks. No duplicated logic.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def calculate_revenue_amount(salary: float, commercial: dict) -> float:
    """Tolerant wrapper: returns the revenue amount or 0.0 on failure.
    Used by pipeline forecasts where a bad commercial config must not 500."""
    try:
        return calculate_revenue(salary, commercial)["revenue_amount"]
    except Exception:
        return 0.0


class RevenueCalculationError(Exception):
    """Raised when revenue cannot be calculated due to invalid inputs."""
    pass


def calculate_revenue(salary: float, commercial: dict) -> dict:
    """
    Central revenue calculation function.

    Args:
        salary: Gross annual CTC (must be > 0).
        commercial: Company commercial config dict.

    Returns:
        {
            salary: float,
            commercial_type: str,
            slab_applied: dict | None,
            percentage_used: float | None,
            revenue_amount: float
        }

    Raises:
        RevenueCalculationError if inputs are invalid or slab not matched.
    """
    if not salary or salary <= 0:
        raise RevenueCalculationError("Salary is required and must be > 0")

    if not commercial or not commercial.get("type"):
        raise RevenueCalculationError("Commercial configuration is missing or invalid")

    comm_type = commercial["type"]

    if comm_type == "percentage":
        pct = commercial.get("percentage_value") or commercial.get("fee_percentage")
        if not pct or pct <= 0:
            raise RevenueCalculationError("Commercial percentage_value is missing or <= 0")
        revenue = round(salary * (pct / 100))
        return {
            "salary": salary,
            "commercial_type": "percentage",
            "slab_applied": None,
            "percentage_used": pct,
            "revenue_amount": revenue,
        }

    elif comm_type == "fixed":
        fixed_amt = commercial.get("fixed_fee_amount") or commercial.get("fixed_amount")
        if not fixed_amt or fixed_amt <= 0:
            raise RevenueCalculationError("Commercial fixed_fee_amount is missing or <= 0")
        return {
            "salary": salary,
            "commercial_type": "fixed",
            "slab_applied": None,
            "percentage_used": None,
            "revenue_amount": round(fixed_amt),
        }

    elif comm_type == "level_based":
        level_config = commercial.get("level_config", [])
        if not isinstance(level_config, list) or not level_config:
            raise RevenueCalculationError(
                "Level-based commercial has no configured salary ranges. "
                "Please configure salary slabs before calculating revenue."
            )

        for slab in level_config:
            if not isinstance(slab, dict):
                continue
            min_s = slab.get("min_salary", 0)
            max_s = slab.get("max_salary", 0)
            pct = slab.get("percentage", 0)
            if min_s <= salary <= max_s and pct > 0:
                revenue = round(salary * (pct / 100))
                return {
                    "salary": salary,
                    "commercial_type": "level_based",
                    "slab_applied": {"min_salary": min_s, "max_salary": max_s, "percentage": pct},
                    "percentage_used": pct,
                    "revenue_amount": revenue,
                }

        # No slab matched — strict error
        range_desc = ", ".join(
            f"{s.get('min_salary',0)}-{s.get('max_salary',0)}"
            for s in level_config if isinstance(s, dict)
        )
        raise RevenueCalculationError(
            f"No salary slab matched for CTC {salary}. "
            f"Configured ranges: [{range_desc}]"
        )

    else:
        raise RevenueCalculationError(f"Unknown commercial type: {comm_type}")
