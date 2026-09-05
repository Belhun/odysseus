"""Migration and database errors for the SysForge plugin."""

from __future__ import annotations

from datetime import datetime
from typing import Any


class ChecksumMismatchError(Exception):
    """Raised when an applied migration file no longer matches its stored checksum.

    Error code matches desktop SysForge: MIGR-CHK-001.
    """

    ERROR_CODE = "MIGR-CHK-001"

    def __init__(
        self,
        migration_id: int,
        migration_name: str,
        applied_at: str,
        applied_checksum: str,
        current_checksum: str,
        database_path: str,
        environment: str = "Development",
    ) -> None:
        self.migration_id = migration_id
        self.migration_name = migration_name
        self.applied_at = applied_at
        self.applied_checksum = applied_checksum
        self.current_checksum = current_checksum
        self.database_path = database_path
        self.environment = environment
        self.error_code = self.ERROR_CODE
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        is_dev = self.environment.lower() == "development"
        recovery = (
            "[DEVELOPMENT MODE]\n"
            "Delete the plugin database and re-run install/migrate:\n"
            f"  {self.database_path}\n"
            "Then call run_install() or run_migrations() again."
            if is_dev
            else "[PRODUCTION MODE]\n"
            "Do not delete the database. Append a new corrective migration "
            "instead of editing applied SQL files."
        )
        return (
            "Migration Checksum Mismatch Detected\n"
            "=====================================\n\n"
            f"Error Code: {self.ERROR_CODE}\n"
            f"Migration: {self.migration_name} (ID: {self.migration_id})\n"
            f"Applied: {self.applied_at} UTC\n"
            f"Database: {self.database_path}\n"
            f"Environment: {self.environment}\n\n"
            "Checksum Mismatch:\n"
            f"  Expected: {self.applied_checksum} (from database)\n"
            f"  Actual:   {self.current_checksum} (from current file)\n\n"
            "This migration was modified after it was applied. "
            "Applied migrations are immutable.\n\n"
            f"RECOVERY OPTIONS:\n\n{recovery}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.ERROR_CODE,
            "migration_id": self.migration_id,
            "migration_name": self.migration_name,
            "applied_at": self.applied_at,
            "applied_checksum": self.applied_checksum,
            "current_checksum": self.current_checksum,
            "environment": self.environment,
        }


class MigrationError(Exception):
    """Generic migration failure."""
