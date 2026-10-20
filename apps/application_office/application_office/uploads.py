"""Secure upload handling for customer/staff documents."""
from __future__ import annotations

import hashlib
import re
import socket
import struct

import frappe
from frappe import _
from frappe.utils import now_datetime

from application_office.common import settings, split_csv

_MAGIC = {"pdf": (b"%PDF-",), "jpg": (b"\xff\xd8\xff",), "jpeg": (b"\xff\xd8\xff",),
          "png": (b"\x89PNG\r\n\x1a\n",)}
_MIME = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}
_PDF_ACTIVE = (b"/JavaScript", b"/JS ", b"/Launch", b"/EmbeddedFile", b"/RichMedia")


class UploadRejected(frappe.ValidationError):
    pass


def validate(filename: str, content: bytes) -> tuple[str, str]:
    """Return (extension, content_type) or raise UploadRejected. Extension alone is never trusted."""
    s = settings()
    if not content:
        frappe.throw(_("The file is empty"), UploadRejected)
    if len(content) > int(s.max_upload_mb) * 1024 * 1024:
        frappe.throw(_("The file exceeds the {0} MB limit").format(s.max_upload_mb), UploadRejected)
    ext = (filename.rsplit(".", 1)[-1] if "." in (filename or "") else "").lower()
    allowed = {e.lower().lstrip(".") for e in split_csv(s.allowed_extensions)}
    if ext not in allowed or ext not in _MAGIC:
        frappe.throw(_("This file type is not accepted"), UploadRejected)
    if not any(content.startswith(m) for m in _MAGIC[ext]):
        frappe.throw(_("The file content does not match its extension"), UploadRejected)
    if ext == "pdf" and any(tok in content for tok in _PDF_ACTIVE):
        frappe.throw(_("PDF files containing scripts or embedded files are not accepted"), UploadRejected)
    if ext == "pdf":
        try:
            from io import BytesIO

            from pypdf import PdfReader
            reader = PdfReader(BytesIO(content), strict=False)
            if len(reader.pages) < 1 or reader.is_encrypted:
                raise ValueError
        except Exception:
            frappe.throw(_("The PDF could not be read or is password-protected"), UploadRejected)
    scan(content)
    return ext, _MIME[ext]


def scan(content: bytes):
    """Optional ClamAV scan via clamd UNIX socket. Fail closed when configured but unreachable."""
    sock_path = settings().clamav_socket
    if not sock_path:
        return
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(20)
            s.connect(sock_path)
            s.sendall(b"zINSTREAM\0")
            for i in range(0, len(content), 8192):
                chunk = content[i:i + 8192]
                s.sendall(struct.pack("!I", len(chunk)) + chunk)
            s.sendall(struct.pack("!I", 0))
            reply = s.recv(4096)
    except OSError:
        frappe.throw(_("Virus scanning is unavailable; please try again later"), UploadRejected)
    if b"FOUND" in reply:
        frappe.throw(_("The file was rejected by the virus scanner"), UploadRejected)
    if b"OK" not in reply:
        frappe.throw(_("Virus scanning failed; please try again later"), UploadRejected)


def store_version(req_doc, filename: str, content: bytes, uploaded_by: str | None = None):
    """Validate, save as a PRIVATE File and append a new immutable version row."""
    ext, content_type = validate(filename, content)
    version = (req_doc.current_version or 0) + 1
    digest = hashlib.sha256(content).hexdigest()
    safe_cat = re.sub(r"[^a-z0-9]+", "-", (req_doc.document_category or "doc").lower()).strip("-")[:30]
    stored_name = f"{req_doc.case}-{safe_cat}-v{version}-{digest[:8]}.{ext}"
    file_doc = frappe.get_doc({
        "doctype": "File", "file_name": stored_name, "is_private": 1, "content": content,
        "attached_to_doctype": "AO Required Document", "attached_to_name": req_doc.name,
        "attached_to_field": None, "folder": "Home/Attachments",
    })
    file_doc.flags.ignore_permissions = True
    file_doc.insert(ignore_permissions=True)
    if not file_doc.is_private or not file_doc.file_url.startswith("/private/"):
        frappe.throw(_("Internal error: file was not stored privately"))
    req_doc.append("versions", {
        "version": version, "file": file_doc.name, "original_filename": (filename or "")[:120],
        "sha256": digest, "size_bytes": len(content), "content_type": content_type,
        "uploaded_by": uploaded_by or frappe.session.user, "uploaded_at": now_datetime()})
    req_doc.current_version = version
    req_doc.upload_status = "Uploaded"
    req_doc.review_status = "Pending"
    req_doc.customer_feedback = None
    req_doc.flags.ao_internal = True
    req_doc.save(ignore_permissions=True)
    return file_doc
