"""Persist generated invoice PDFs under plugin data/documents/."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

from src.plugins import registry

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.utc import format_storage
from integrations.sysforge.pdf_invoice import (
    generate_invoice_pdf,
    suggested_pdf_filename,
)
from integrations.sysforge.services.invoices import InvoiceNotFoundError


def documents_root() -> Path:
    path = registry.plugin_data_dir("sysforge") / "documents"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _row_to_doc(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    return {
        "id": int(data["Id"]),
        "invoice_id": int(data["InvoiceId"]),
        "kind": data.get("Kind") or "pdf",
        "file_name": data.get("FileName") or "",
        "mime_type": data.get("MimeType") or "application/pdf",
        "size_bytes": int(data.get("SizeBytes") or 0),
        "stored_rel_path": data.get("StoredRelPath") or "",
        "sha256": data.get("Sha256"),
        "created_at": data.get("CreatedAt"),
    }


def persist_pdf(
    invoice_id: int,
    pdf_bytes: bytes,
    *,
    file_name: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Write PDF to disk and insert InvoiceDocuments row."""
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("Not a PDF")
    name = file_name or f"invoice-{invoice_id}.pdf"
    safe_name = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in name)
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    rel = f"invoices/{invoice_id}/{sha[:16]}_{safe_name}"
    abs_path = documents_root() / rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(pdf_bytes)

    own = conn is None
    if own:
        conn = db_connection.connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO InvoiceDocuments (
              InvoiceId, Kind, FileName, MimeType, SizeBytes,
              StoredRelPath, Sha256, CreatedAt
            ) VALUES (?, 'pdf', ?, 'application/pdf', ?, ?, ?, ?)
            """,
            (
                invoice_id,
                safe_name,
                len(pdf_bytes),
                rel.replace("\\", "/"),
                sha,
                format_storage(),
            ),
        )
        doc_id = int(cur.lastrowid)
        if own:
            conn.commit()
        row = conn.execute(
            "SELECT * FROM InvoiceDocuments WHERE Id = ?", (doc_id,)
        ).fetchone()
        return _row_to_doc(row)
    finally:
        if own:
            conn.close()


def generate_and_persist(invoice_id: int) -> tuple[bytes, dict[str, Any], dict[str, Any]]:
    """Generate PDF, persist metadata, return (bytes, invoice, document_row)."""
    pdf_bytes, invoice = generate_invoice_pdf(invoice_id)
    doc = persist_pdf(
        invoice_id,
        pdf_bytes,
        file_name=suggested_pdf_filename(invoice),
    )
    return pdf_bytes, invoice, doc


def resolve_stored_path(rel: str) -> Path:
    """Resolve a StoredRelPath under documents root (no traversal)."""
    root = documents_root().resolve()
    candidate = (root / rel).resolve()
    if not str(candidate).startswith(str(root)):
        raise ValueError("Invalid document path")
    return candidate


__all__ = [
    "InvoiceNotFoundError",
    "documents_root",
    "generate_and_persist",
    "persist_pdf",
    "resolve_stored_path",
]
