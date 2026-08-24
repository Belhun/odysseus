"""Investing holdings models. Manual posted values; not bank CSV."""

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text

from integrations.finance.models import FinanceBase, TimestampMixin, utcnow_naive

ASSET_KINDS = ("stock", "etf", "fund", "crypto", "cash", "other")


class FinanceInvestAsset(TimestampMixin, FinanceBase):
    __tablename__ = "finance_invest_assets"
    __table_args__ = (
        Index("ix_finance_invest_assets_owner_archived", "owner", "archived"),
    )

    id = Column(String, primary_key=True, index=True)
    owner = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    symbol = Column(String, default="", nullable=False)
    asset_kind = Column(String, nullable=False, default="other")
    account_id = Column(
        String,
        ForeignKey("finance_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    shares_millishares = Column(Integer, nullable=False, default=0)
    cost_basis_cents = Column(Integer, nullable=False, default=0)
    current_value_cents = Column(Integer, nullable=False, default=0)
    notes = Column(Text, default="", nullable=False)
    archived = Column(Boolean, default=False, nullable=False)


class FinanceInvestValuation(FinanceBase):
    __tablename__ = "finance_invest_valuations"
    __table_args__ = (
        Index("ix_finance_invest_valuations_asset_as_of", "asset_id", "as_of"),
    )

    id = Column(String, primary_key=True, index=True)
    owner = Column(String, nullable=False, index=True)
    asset_id = Column(
        String,
        ForeignKey("finance_invest_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    as_of = Column(Date, nullable=False)
    value_cents = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=utcnow_naive, nullable=False)
