"""Portable backup / JSON export models (SysForgeExportData v1.0).

Business backup is scoped to ``data/plugins/sysforge/`` and is separate from
Odysseus global ``/api/export`` (memories, presets, skills, host settings).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EXPORT_VERSION = "1.0"

ConflictMode = Literal["skip", "overwrite"]

SQL_IMPORT_REJECT_MESSAGE = (
    "SQL dump import is not supported. Use portable JSON or a Business .db / ZIP backup."
)


@dataclass
class ImportOptions:
    import_clients: bool = True
    import_invoices: bool = True
    import_invoice_items: bool = True
    import_parts: bool = True
    import_settings: bool = True
    conflict: ConflictMode = "skip"

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> ImportOptions:
        raw = data or {}
        conflict = str(raw.get("conflict") or "skip").strip().lower()
        if conflict not in ("skip", "overwrite"):
            conflict = "skip"
        return cls(
            import_clients=_as_bool(raw.get("import_clients"), True),
            import_invoices=_as_bool(raw.get("import_invoices"), True),
            import_invoice_items=_as_bool(raw.get("import_invoice_items"), True),
            import_parts=_as_bool(raw.get("import_parts"), True),
            import_settings=_as_bool(raw.get("import_settings"), True),
            conflict=conflict,  # type: ignore[arg-type]
        )


@dataclass
class ImportResult:
    success: bool = False
    message: str = ""
    clients_imported: int = 0
    clients_skipped: int = 0
    invoices_imported: int = 0
    invoices_skipped: int = 0
    invoice_items_imported: int = 0
    parts_imported: int = 0
    parts_skipped: int = 0
    payments_imported: int = 0
    invoice_documents_imported: int = 0
    settings_imported: bool = False
    search_rebuilt: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BackupInfo:
    id: str
    filename: str
    size_bytes: int
    created_at: str
    has_config: bool = False
    has_drafts: bool = False
    kind: str = "zip"  # zip | db

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BackupResult:
    success: bool = False
    message: str = ""
    backup: BackupInfo | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "ok": self.success,
            "message": self.message,
            "backup": self.backup.to_dict() if self.backup else None,
        }


@dataclass
class RestoreResult:
    success: bool = False
    message: str = ""
    safety_backup_id: str | None = None
    search_rebuilt: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "ok": self.success,
            "message": self.message,
            "safety_backup_id": self.safety_backup_id,
            "search_rebuilt": self.search_rebuilt,
        }


@dataclass
class BackupSchedule:
    schedule_enabled: bool = False
    schedule_interval_days: int = 7
    retention_days: int = 30
    include_drafts: bool = False
    last_run_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return default


# Desktop enum ordinals → CHECK text (sample-export.json uses ints).
STATUS_FROM_INT = {0: "Estimate", 1: "Invoiced", 2: "Paid"}
STATUS_TEXT = frozenset({"Estimate", "Invoiced", "Paid"})
DISCOUNT_FROM_INT = {0: "None", 1: "Percent", 2: "Amount"}
DISCOUNT_TEXT = frozenset({"None", "Percent", "Amount"})
ITEM_TYPE_FROM_INT = {0: "Part", 1: "Labor", 2: "Misc"}
ITEM_TYPE_TEXT = frozenset({"Part", "Labor", "Misc"})


def map_status(value: Any) -> str:
    if isinstance(value, int):
        return STATUS_FROM_INT.get(value, "Estimate")
    text = str(value or "Estimate").strip()
    if text.isdigit():
        return STATUS_FROM_INT.get(int(text), "Estimate")
    if text in STATUS_TEXT:
        return text
    # Case-insensitive
    for name in STATUS_TEXT:
        if name.lower() == text.lower():
            return name
    return "Estimate"


def map_discount_type(value: Any) -> str:
    if isinstance(value, int):
        return DISCOUNT_FROM_INT.get(value, "None")
    text = str(value or "None").strip()
    if text.isdigit():
        return DISCOUNT_FROM_INT.get(int(text), "None")
    if text in DISCOUNT_TEXT:
        return text
    for name in DISCOUNT_TEXT:
        if name.lower() == text.lower():
            return name
    return "None"


def map_item_type(value: Any) -> str:
    if isinstance(value, int):
        return ITEM_TYPE_FROM_INT.get(value, "Part")
    text = str(value or "Part").strip()
    if text.isdigit():
        return ITEM_TYPE_FROM_INT.get(int(text), "Part")
    if text in ITEM_TYPE_TEXT:
        return text
    for name in ITEM_TYPE_TEXT:
        if name.lower() == text.lower():
            return name
    return "Part"


DEFAULT_BACKUP_SCHEDULE: dict[str, Any] = {
    "schedule_enabled": False,
    "schedule_interval_days": 7,
    "retention_days": 30,
    "include_drafts": False,
    "last_run_at": None,
}
