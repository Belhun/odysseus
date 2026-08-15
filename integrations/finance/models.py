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


ACCOUNT_PURPOSES = ("operating", "trip", "processor")
ACCOUNT_RAILS = ("paypal", "venmo", "google")
TX_STATUSES = ("pending", "cleared", "reconciled", "void")
TX_SOURCES = ("import", "manual")
MOVEMENT_CLASSES = ("spend", "income", "transfer", "pass_through", "reimbursement")
PLANNED_KINDS = (
    "rent",
    "utilities",
    "insurance",
    "telecom",
    "reimbursement_swap",
    "savings_funding",
    "other",
)
RECURRING_STATUSES = ("active", "automatic", "dismissed")


class FinanceAccount(TimestampMixin, FinanceBase):
    __tablename__ = "finance_accounts"

    id = Column(String, primary_key=True, index=True)
    owner = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    institution = Column(String, default="")
    account_type = Column(String, nullable=False, default="checking")
    purpose = Column(String, nullable=False, default="operating")
    rail = Column(String, nullable=True)
    currency = Column(String, default="USD")
    mask_last4 = Column(String, nullable=True)
    opening_balance_cents = Column(Integer, default=0)
    opening_balance_date = Column(Date, nullable=True)
    credit_limit_cents = Column(Integer, nullable=True)
    posted_pin_cents = Column(Integer, nullable=True)
    posted_pin_as_of = Column(Date, nullable=True)
    available_cents = Column(Integer, nullable=True)
    available_as_of = Column(Date, nullable=True)
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
        Index("ix_finance_tx_account_dedup", "account_id", "dedup_hash", unique=True),
        Index("ix_finance_tx_owner_date", "owner", "date"),
        Index("ix_finance_tx_owner_class_date", "owner", "movement_class", "date"),
        Index("ix_finance_tx_owner_group", "owner", "movement_group_id"),
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
    source = Column(String, default="import")
    bank_category = Column(String, nullable=True)
    movement_class = Column(String, nullable=True)
    movement_group_id = Column(String, nullable=True)

    account = relationship("FinanceAccount", back_populates="transactions")


class FinanceCategorizationRule(TimestampMixin, FinanceBase):
    __tablename__ = "finance_categorization_rules"

    id = Column(String, primary_key=True, index=True)
    owner = Column(String, nullable=False, index=True)
    pattern = Column(String, nullable=False)
    category_id = Column(String, ForeignKey("finance_categories.id"), nullable=False)
    priority = Column(Integer, default=100)


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


class FinanceRecurringSeries(TimestampMixin, FinanceBase):
    __tablename__ = "finance_recurring_series"
    __table_args__ = (
        Index(
            "ix_finance_recurring_owner_payee",
            "owner",
            "normalized_payee",
            unique=True,
        ),
    )

    id = Column(String, primary_key=True, index=True)
    owner = Column(String, nullable=False, index=True)
    normalized_payee = Column(String, nullable=False)
    display_payee = Column(String, default="")
    cadence = Column(String, nullable=False)
    interval_days = Column(Integer, nullable=False)
    median_amount_cents = Column(Integer, nullable=False)
    next_due_date = Column(Date, nullable=True)
    status = Column(String, default="active")
    category_id = Column(String, ForeignKey("finance_categories.id"), nullable=True)
    movement_class = Column(String, nullable=True)


class FinanceTransactionSplit(TimestampMixin, FinanceBase):
    __tablename__ = "finance_transaction_splits"

    id = Column(String, primary_key=True, index=True)
    owner = Column(String, nullable=False, index=True)
    transaction_id = Column(String, ForeignKey("finance_transactions.id"), nullable=False, index=True)
    category_id = Column(String, ForeignKey("finance_categories.id"), nullable=True)
    amount_cents = Column(Integer, nullable=False)
    memo = Column(String, default="")


class FinanceMutationLog(TimestampMixin, FinanceBase):
    __tablename__ = "finance_mutation_log"

    id = Column(String, primary_key=True, index=True)
    owner = Column(String, nullable=False, index=True)
    actor = Column(String, nullable=False, default="user")
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False, index=True)
    before_json = Column(Text, nullable=True)
    after_json = Column(Text, nullable=True)


class FinanceCsvMapping(TimestampMixin, FinanceBase):
    __tablename__ = "finance_csv_mappings"
    __table_args__ = (
        Index("ix_finance_csv_map_owner_fp", "owner", "fingerprint", unique=True),
    )

    id = Column(String, primary_key=True, index=True)
    owner = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    fingerprint = Column(String, nullable=False)
    mapping = Column(JSON, nullable=False)
    options = Column(JSON, nullable=True)


class FinanceMonthSettings(TimestampMixin, FinanceBase):
    __tablename__ = "finance_month_settings"
    __table_args__ = (
        Index("ix_finance_month_settings_owner_month", "owner", "month", unique=True),
    )

    id = Column(String, primary_key=True, index=True)
    owner = Column(String, nullable=False, index=True)
    month = Column(String, nullable=False)
    income_target_cents = Column(Integer, nullable=False, default=0)


class FinancePlannedObligation(TimestampMixin, FinanceBase):
    __tablename__ = "finance_planned_obligations"

    id = Column(String, primary_key=True, index=True)
    owner = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    kind = Column(String, nullable=False)
    amount_cents = Column(Integer, nullable=False)
    cadence = Column(String, nullable=False, default="monthly")
    starts_on = Column(String, nullable=True)
    include_in_job_overlay = Column(Boolean, default=True)
    is_funding = Column(Boolean, default=False)
    notes = Column(String, default="")


class FinanceJobScenario(TimestampMixin, FinanceBase):
    __tablename__ = "finance_job_scenarios"

    id = Column(String, primary_key=True, index=True)
    owner = Column(String, nullable=False, unique=True, index=True)
    take_home_cents = Column(Integer, nullable=False, default=0)
    label = Column(String, nullable=False, default="Hypothetical job")
