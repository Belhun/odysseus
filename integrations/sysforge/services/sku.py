"""SKU normalize + conflict error (desktop SkuConflictException parity)."""

from __future__ import annotations

from typing import Any


def normalize_sku(sku: str | None) -> str | None:
    """Trim; whitespace-only → None (never store empty string)."""
    if sku is None:
        return None
    trimmed = sku.strip()
    return trimmed if trimmed else None


class SkuConflictError(Exception):
    """Raised when a SKU is already used by another part."""

    def __init__(self, sku: str, conflicting_part: dict[str, Any]) -> None:
        self.sku = sku
        self.conflicting_part = conflicting_part
        super().__init__(f"SKU already exists: {sku}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "detail": "SKU already exists",
            "code": "sku_conflict",
            "sku": self.sku,
            "conflicting_part": self.conflicting_part,
        }
