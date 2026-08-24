"""Goals table — progress is computed, never a second ledger."""

from sqlalchemy import Boolean, Column, Date, Integer, String

from integrations.finance.models import FinanceBase, TimestampMixin

GOAL_KINDS = ("account", "category", "loan")


class FinanceGoal(TimestampMixin, FinanceBase):
    __tablename__ = "finance_goals"

    id = Column(String, primary_key=True, index=True)
    owner = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    kind = Column(String, nullable=False, default="account")
    target_cents = Column(Integer, nullable=False, default=0)
    target_date = Column(Date, nullable=True)
    account_id = Column(String, nullable=True, index=True)
    category_id = Column(String, nullable=True, index=True)
    baseline_cents = Column(Integer, nullable=False, default=0)
    icon = Column(String, nullable=True)
    color = Column(String, default="#5b8abf")
    archived = Column(Boolean, default=False)
