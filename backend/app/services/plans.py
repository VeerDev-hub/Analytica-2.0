"""Subscription plans.

One free tier and two paid tiers. The plan decides the storage limit and whether the AI
assistant is available. Prices here are display values; billing is not wired to a payment
provider yet, so an admin assigns plans in Admin → Users and the "Upgrade" button sends
users to the URL set in Admin → Settings (a payment link or a contact page).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

GB = 1024**3


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    price_month_usd: int
    storage_gb: int
    assistant: bool
    tagline: str
    features: tuple[str, ...]


PLANS: dict[str, Plan] = {
    "free": Plan(
        id="free",
        name="Free",
        price_month_usd=0,
        storage_gb=3,
        assistant=False,
        tagline="For trying things out and small datasets.",
        features=(
            "3 GB of storage",
            "Unlimited projects",
            "Every cleaning and feature step",
            "Readiness checks and baseline models",
            "All export formats, including the reproducible script",
            "Recipes",
        ),
    ),
    "pro": Plan(
        id="pro",
        name="Pro",
        price_month_usd=12,
        storage_gb=25,
        assistant=True,
        tagline="For analysts and students who work with data every week.",
        features=(
            "25 GB of storage",
            "AI assistant: ask questions in plain language",
            "Everything in Free",
        ),
    ),
    "business": Plan(
        id="business",
        name="Business",
        price_month_usd=39,
        storage_gb=100,
        assistant=True,
        tagline="For teams with larger datasets and heavier use.",
        features=(
            "100 GB of storage",
            "AI assistant with a higher daily limit",
            "Everything in Pro",
        ),
    ),
}

DEFAULT_PLAN = "free"
ORDER = ("free", "pro", "business")

# Assistant messages per user per day (admins are not limited).
ASSISTANT_DAILY_LIMIT = {"free": 0, "pro": 200, "business": 1000}


def get_plan(plan_id: str | None) -> Plan:
    return PLANS.get(plan_id or DEFAULT_PLAN, PLANS[DEFAULT_PLAN])


def plan_for(user) -> Plan:
    return get_plan(getattr(user, "plan", None))


def storage_bytes(plan: Plan) -> int:
    return plan.storage_gb * GB


def assistant_allowed(user) -> bool:
    """Admins always have the assistant so they can test it."""
    return getattr(user, "role", "") == "admin" or plan_for(user).assistant


def catalog() -> list[dict]:
    return [asdict(PLANS[p]) for p in ORDER]
