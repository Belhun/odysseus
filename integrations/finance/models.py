"""Plugin-local SQLAlchemy models for Finance."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import declarative_base, relationship


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


FinanceBase = declarative_base()


class TimestampMixin:
    created_at = Column(DateTime, default=utcnow_naive, nullable=False)
    updated_at = Column(DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False)


class FinanceAccount(TimestampMixin, FinanceBase):
    __tablename__ = "finance_accounts"

    id = Column(String, primary_key=True, index=True)
    owner = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    institution = Column(String, default="")
    account_type = Column(String, nullable=False, default="checking")
    currency = Column(String, default="USD")
    mask_last4 = Column(String, nullable=True)
    opening_balance_cents = Column(Integer, default=0)
    opening_balance_date = Column(Date, nullable=True)
    credit_limit_cents = Column(Integer, nullable=True)
    is_closed = Column(Boolean, default=False)
    display_order = Column(Integer, default=0)

    transactions = relationship(
        "FinanceTransaction",
        back_populates="account",
        cascade="all, delete-orphan",
    )


class FinanceCategory(TimestampMixin, FinanceBase):
    __tablename__ = "finance_categories"

    id = Column(String, primary_key=True, index=True)
    owner = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    parent_id = Column(String, ForeignKey("finance_categories.id"), nullable=True)
    is_income = Column(Boolean, default=False)
    display_order = Column(Integer, default=0)
    color = Column(String, default="#5b8abf")


class FinanceImportBatch(TimestampMixin, FinanceBase):
    __tablename__ = "finance_import_batches"

    id = Column(String, primary_key=True, index=True)
    owner = Column(String, nullable=False, index=True)
    account_id = Column(String, ForeignKey("finance_accounts.id"), nullable=False, index=True)
    filename = Column(String, default="")
    format = Column(String, default="csv_generic")
    row_count = Column(Integer, default=0)
    imported_count = Column(Integer, default=0)
    duplicate_count = Column(Integer, default=0)


class FinanceImportPreview(TimestampMixin, FinanceBase):
    __tablename__ = "finance_import_previews"

    id = Column(String, primary_key=True, index=True)
    owner = Column(String, nullable=False, index=True)
    account_id = Column(String, ForeignKey("finance_accounts.id"), nullable=True)
    filename = Column(String, default="")
    format = Column(String, default="csv_generic")
    payload = Column(JSON, nullable=False)


class FinanceTransaction(TimestampMixin, FinanceBase):
    __tablename__ = "finance_transactions"
    __table_args__ = (
        Index("ix_finance_tx_account_dedup", "account_id", "dedup_hash"),
        Index("ix_finance_tx_owner_date", "owner", "date"),
    )

    id = Column(String, primary_key=True, index=True)
    owner = Column(String, nullable=False, index=True)
    account_id = Column(String, ForeignKey("finance_accounts.id"), nullable=False, index=True)
    import_batch_id = Column(String, ForeignKey("finance_import_batches.id"), nullable=True, index=True)
    date = Column(Date, nullable=False)
    amount_cents = Column(Integer, nullable=False)
    payee = Column(String, default="")
    memo = Column(String, default="")
    check_number = Column(String, nullable=True)
    fitid = Column(String, nullable=True)
    dedup_hash = Column(String, nullable=False)
    category_id = Column(String, ForeignKey("finance_categories.id"), nullable=True, index=True)
    status = Column(String, default="cleared")
    bank_category = Column(String, nullable=True)

    account = relationship("FinanceAccount", back_populates="transactions")


class FinanceCategorizationRule(TimestampMixin, FinanceBase):
    __tablename__ = "finance_categorization_rules"

    id = Column(String, primary_key=True, index=True)
    owner = Column(String, nullable=False, index=True)
    pattern = Column(String, nullable=False)
    category_id = Column(String, ForeignKey("finance_categories.id"), nullable=False)
    priority = Column(Integer, default=0)


class FinanceCategoryBudget(TimestampMixin, FinanceBase):
    __tablename__ = "finance_category_budgets"
    __table_args__ = (
        Index("ix_finance_budget_owner_month_cat", "owner", "month", "category_id", unique=True),
    )

    id = Column(String, primary_key=True, index=True)
    owner = Column(String, nullable=False, index=True)
    category_id = Column(String, ForeignKey("finance_categories.id"), nullable=False)
    month = Column(String, nullable=False)
    limit_cents = Column(Integer, nullable=False, default=0)
