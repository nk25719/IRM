from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import UTC, datetime
from typing import Any

from openpyxl import load_workbook
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app import erp_models as erp
from app.models.foundation import Manufacturer, Supplier
from app.models.foundation import AuditEvent, DataValidationError, ImportBatch, ImportRow

SOURCE = "outlook_email_history_import"
EXPECTED_SHEET = "Customer Contacts"
EXPECTED_COLUMNS = ["Name", "Email", "Company / Domain", "Emails Exchanged", "Role", "Phone", "Notes"]
EMAIL_RE = re.compile(r"^[A-Z0-9._%+\-']+@[A-Z0-9.\-]+\.[A-Z]{2,}$", re.I)
PUBLIC_DOMAINS = {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "live.com", "icloud.com"}
SHARED_TERMS = {
    "purchasing": "purchasing",
    "procurement": "purchasing",
    "service": "service",
    "support": "technical_support",
    "sales": "sales",
    "info": "shared_inbox",
    "admin": "administration",
    "finance": "finance",
    "training": "training",
    "reception": "administration",
    "biomedical": "biomedical_engineering",
    "clinicalengineering": "clinical_engineering",
    "clinical.engineering": "clinical_engineering",
}
AUTOMATED_TERMS = {"noreply", "no-reply", "notification", "notifications", "mailer-daemon", "account-security", "learning.notifications", "automated", "system"}


def normalize_email(value: Any) -> str:
    return str(value or "").strip().casefold()


def email_domain(email: str) -> str:
    return email.split("@", 1)[1] if "@" in email else ""


def engagement_level(count: int) -> str:
    if count >= 30:
        return "high"
    if count >= 10:
        return "active"
    if count >= 3:
        return "moderate"
    return "low"


def parse_count(value: Any) -> int:
    try:
        return max(0, int(float(str(value or "0").replace(",", "").strip() or 0)))
    except Exception:
        return 0


def normalize_phone(value: Any) -> tuple[str | None, str | None]:
    original = str(value or "").strip()
    digits = re.sub(r"[^\d+]", "", original)
    return (digits or None, original or None)


def split_name(value: str) -> tuple[str | None, str | None]:
    cleaned = re.sub(r"\s+", " ", value or "").strip()
    if not cleaned or any(term in cleaned.casefold() for term in SHARED_TERMS):
        return None, None
    parts = cleaned.split(" ")
    if 2 <= len(parts) <= 3 and all(re.match(r"^[A-Za-z][A-Za-z'\-]+$", part) for part in parts):
        return parts[0], " ".join(parts[1:])
    return None, None


def detect_shared(display_name: str, email: str) -> tuple[bool, str]:
    text = f"{display_name} {email.split('@', 1)[0] if '@' in email else email}".casefold()
    for term, contact_type in SHARED_TERMS.items():
        if term in text:
            return True, contact_type
    return False, "person"


def detect_automated(display_name: str, email: str) -> bool:
    text = f"{display_name} {email.split('@', 1)[0] if '@' in email else email}".casefold()
    return any(term in text for term in AUTOMATED_TERMS)


def quality_status(normalized: dict[str, Any], messages: list[str]) -> str:
    if not normalized.get("organization_type") or normalized.get("organization_type") == "unknown":
        return "needs_organization_match"
    if normalized.get("is_automated_address") or normalized.get("is_shared_inbox") or messages:
        return "needs_review"
    if not normalized.get("role_title"):
        return "needs_role"
    if not normalized.get("phone"):
        return "needs_phone"
    return "complete"


class CustomerContactsImportService:
    def __init__(self, db: Session, user_id: int | None = None):
        self.db = db
        self.user_id = user_id

    def preview(self, content: bytes, filename: str, sheet_name: str | None = None) -> dict[str, Any]:
        workbook = load_workbook(io.BytesIO(content), data_only=True)
        sheet = workbook[sheet_name] if sheet_name and sheet_name in workbook.sheetnames else workbook[EXPECTED_SHEET] if EXPECTED_SHEET in workbook.sheetnames else workbook.active
        headers = [str(cell.value or "").strip() for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
        header_map = {header: index for index, header in enumerate(headers)}
        rows = []
        issues = []
        batch = ImportBatch(
            source_type="customer_contacts",
            source_filename=filename,
            source_checksum=hashlib.sha256(content).hexdigest(),
            imported_by_id=self.user_id,
            status="preview",
            total_rows=max(0, sheet.max_row - 1),
            notes=json.dumps({"worksheet": sheet.title, "columns": headers}),
        )
        self.db.add(batch)
        self.db.flush()
        for excel_row in sheet.iter_rows(min_row=2, values_only=True):
            raw = {column: excel_row[header_map[column]] if column in header_map and header_map[column] < len(excel_row) else "" for column in EXPECTED_COLUMNS}
            staged = self.stage_row(batch.id, len(rows) + 2, raw)
            rows.append(staged)
            for issue in staged["issues"]:
                if issue["severity"] == "error":
                    issues.append(issue)
        batch.processed_rows = len(rows)
        batch.successful_rows = sum(1 for row in rows if row["import_status"] in {"ready_create", "ready_update", "skipped"})
        batch.failed_rows = sum(1 for row in rows if row["import_status"] == "error")
        self._audit("customer_contacts_preview_generated", "import_batch", str(batch.id), {"filename": filename, "rows": len(rows)})
        self.db.commit()
        return self.import_payload(batch.id)

    def stage_row(self, batch_id: int, row_number: int, raw: dict[str, Any]) -> dict[str, Any]:
        name = str(raw.get("Name") or "").strip()
        imported_email = normalize_email(raw.get("Email"))
        issues: list[dict[str, Any]] = []
        if not imported_email:
            normalized = {"display_name": name, "import_action": "skip", "skip_reason": "domain_heading_or_blank_email"}
            import_row = ImportRow(import_batch_id=batch_id, row_number=row_number, raw_data=raw, normalized_data=normalized, processing_status="skipped", warning_message="Skipped grouping/domain row")
            self.db.add(import_row)
            self.db.flush()
            return self.row_payload(import_row, [])
        if not EMAIL_RE.match(imported_email):
            issues.append(self.issue(row_number, "email", imported_email, "invalid_email", "Email address is invalid", "error"))
        domain = email_domain(imported_email)
        supplied_domain = str(raw.get("Company / Domain") or "").strip().casefold()
        if supplied_domain and supplied_domain != domain and "@" not in supplied_domain:
            issues.append(self.issue(row_number, "company_domain", supplied_domain, "domain_mismatch", "Company / Domain differs from the email-derived domain", "warning"))
        shared, contact_type = detect_shared(name, imported_email)
        automated = detect_automated(name, imported_email)
        phone, phone_original = normalize_phone(raw.get("Phone"))
        first_name, last_name = split_name(name)
        org = self.match_organization(domain)
        count = parse_count(raw.get("Emails Exchanged"))
        existing = self.find_existing(imported_email)
        normalized = {
            "display_name": name,
            "first_name": first_name,
            "last_name": last_name,
            "email": imported_email,
            "normalized_email": imported_email,
            "email_domain": domain,
            "emails_exchanged": count,
            "engagement_level": engagement_level(count),
            "phone": phone,
            "phone_original": phone_original,
            "role_title": str(raw.get("Role") or "").strip() or None,
            "notes": str(raw.get("Notes") or "").strip() or None,
            "is_shared_inbox": shared,
            "is_automated_address": automated,
            "contact_type": "shared_inbox" if automated else contact_type,
            "organization_type": org.get("organization_type", "unknown"),
            "client_id": org.get("client_id"),
            "manufacturer_id": org.get("manufacturer_id"),
            "supplier_id": org.get("supplier_id"),
            "suggested_organization": org.get("name"),
            "existing_contact_id": existing.id if existing else None,
            "import_action": "update_existing_contact" if existing else "create_contact",
            "source": SOURCE,
            "source_reference": json.dumps(raw),
        }
        if not phone:
            issues.append(self.issue(row_number, "phone", "", "phone_missing", "Phone is missing; imported phone numbers require verification when present", "warning"))
        if phone:
            issues.append(self.issue(row_number, "phone", phone_original or phone, "phone_unverified", "Automatically extracted phone requires verification", "warning"))
        if not normalized["role_title"]:
            issues.append(self.issue(row_number, "role", "", "role_missing", "Role is missing and must be enriched manually", "warning"))
        if domain in PUBLIC_DOMAINS:
            normalized["organization_type"] = "personal"
            normalized["client_id"] = normalized["manufacturer_id"] = normalized["supplier_id"] = None
            issues.append(self.issue(row_number, "email_domain", domain, "public_email_domain", "Public email domains are not mapped to organizations automatically", "warning"))
        elif not org:
            issues.append(self.issue(row_number, "email_domain", domain, "organization_match_required", "Domain requires organization review", "warning"))
        normalized["data_quality_status"] = quality_status(normalized, [i["error_code"] for i in issues if i["severity"] == "warning"])
        status = "error" if any(i["severity"] == "error" for i in issues) else normalized["import_action"].replace("_existing_contact", "")
        import_row = ImportRow(import_batch_id=batch_id, row_number=row_number, raw_data=raw, normalized_data=normalized, processing_status=status, matched_client_id=normalized.get("client_id"), warning_message="; ".join(i["error_message"] for i in issues if i["severity"] == "warning") or None, error_message="; ".join(i["error_message"] for i in issues if i["severity"] == "error") or None)
        self.db.add(import_row)
        self.db.flush()
        for item in issues:
            values = dict(item)
            values.pop("row_number", None)
            self.db.add(DataValidationError(import_batch_id=batch_id, import_row_id=import_row.id, **values))
        return self.row_payload(import_row, issues)

    def confirm(self, import_id: int, decisions: list[dict[str, Any]] | None = None) -> dict[str, int]:
        decisions_by_row = {int(item["row_number"]): item for item in decisions or [] if item.get("row_number")}
        batch = self.db.get(ImportBatch, import_id)
        if not batch or batch.source_type != "customer_contacts":
            raise LookupError("Customer contacts import not found")
        created = updated = rejected = ignored = 0
        try:
            for row in self.db.query(ImportRow).filter_by(import_batch_id=import_id).order_by(ImportRow.row_number).all():
                data = dict(row.normalized_data or {})
                decision = decisions_by_row.get(row.row_number, {})
                action = decision.get("action") or data.get("import_action")
                if row.processing_status == "error" or action in {"reject", "rejected"}:
                    row.processing_status = "rejected"
                    rejected += 1
                    self._audit("customer_contact_rejected", "import_row", str(row.id), {"row_number": row.row_number, "reason": decision.get("reason")})
                    continue
                if action in {"ignore", "skip"} or row.processing_status == "skipped":
                    row.processing_status = "skipped"
                    ignored += 1
                    continue
                self.apply_decision(data, decision)
                contact, was_created = self.upsert_contact(data)
                row.processing_status = "imported"
                row.processed_at = datetime.now(UTC)
                if was_created:
                    created += 1
                    self._audit("customer_contact_created", "contact", str(contact.id), {"row_number": row.row_number, "contact_id": contact.id, "email": contact.email})
                else:
                    updated += 1
                    self._audit("customer_contact_updated", "contact", str(contact.id), {"row_number": row.row_number, "contact_id": contact.id, "email": contact.email})
            batch.status = "completed"
            batch.completed_at = datetime.now(UTC)
            batch.processed_rows = created + updated + rejected + ignored
            batch.successful_rows = created + updated
            batch.failed_rows = rejected
            self._audit("customer_contacts_import_confirmed", "import_batch", str(import_id), {"created": created, "updated": updated, "rejected": rejected, "ignored": ignored})
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {"created": created, "updated": updated, "rejected": rejected, "ignored": ignored}

    def upsert_contact(self, data: dict[str, Any]) -> tuple[erp.Contact, bool]:
        contact = self.find_existing(data["normalized_email"])
        created = contact is None
        if created:
            contact = erp.Contact(name=data.get("display_name") or data["email"], email=data["email"], normalized_email=data["normalized_email"])
            self.db.add(contact)
        old_phone = contact.phone
        contact.display_name = contact.display_name or data.get("display_name")
        contact.name = contact.name or data.get("display_name") or data["email"]
        contact.first_name = contact.first_name or data.get("first_name")
        contact.last_name = contact.last_name or data.get("last_name")
        contact.email = data["email"]
        contact.normalized_email = data["normalized_email"]
        contact.email_domain = data.get("email_domain")
        contact.role_title = contact.role_title or data.get("role_title")
        contact.title = contact.title or data.get("role_title")
        if not contact.phone or (not contact.phone_verified and data.get("phone")):
            contact.phone = data.get("phone") or contact.phone
            contact.phone_original = data.get("phone_original") or contact.phone_original
        else:
            contact.phone = old_phone
        if int(data.get("emails_exchanged") or 0) > int(contact.emails_exchanged or 0):
            contact.emails_exchanged = data.get("emails_exchanged")
            contact.engagement_level = data.get("engagement_level")
        contact.contact_type = data.get("contact_type") or contact.contact_type
        contact.organization_type = data.get("organization_type") or contact.organization_type
        for field in ("client_id", "manufacturer_id", "supplier_id", "client_site_id"):
            if getattr(contact, field, None) is None and data.get(field):
                setattr(contact, field, data.get(field))
        contact.is_shared_inbox = bool(data.get("is_shared_inbox"))
        contact.is_automated_address = bool(data.get("is_automated_address"))
        contact.source = SOURCE
        contact.source_reference = data.get("source_reference")
        contact.data_quality_status = data.get("data_quality_status") or contact.data_quality_status
        contact.last_imported_at = datetime.now(UTC)
        if data.get("notes") and not contact.notes:
            contact.notes = data["notes"]
        self.db.flush()
        return contact, created

    def import_payload(self, import_id: int) -> dict[str, Any]:
        batch = self.db.get(ImportBatch, import_id)
        if not batch:
            raise LookupError("Import not found")
        rows = [self.row_payload(row) for row in self.db.query(ImportRow).filter_by(import_batch_id=import_id).order_by(ImportRow.row_number).all()]
        return {
            "import_id": batch.id,
            "filename": batch.source_filename,
            "status": batch.status,
            "total_rows": batch.total_rows,
            "processed_rows": batch.processed_rows,
            "successful_rows": batch.successful_rows,
            "failed_rows": batch.failed_rows,
            "rows": rows,
            "metrics": self.metrics(rows),
        }

    def report_csv(self, import_id: int) -> bytes:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Import status", "Name", "Email", "Domain", "Emails exchanged", "Engagement level", "Phone", "Role", "Suggested organization", "Organization type", "Shared inbox", "Automated address", "Data-quality status", "Validation messages", "Import action"])
        for row in self.import_payload(import_id)["rows"]:
            writer.writerow([row.get("import_status"), row.get("display_name"), row.get("email"), row.get("email_domain"), row.get("emails_exchanged"), row.get("engagement_level"), row.get("phone"), row.get("role_title"), row.get("suggested_organization"), row.get("organization_type"), row.get("is_shared_inbox"), row.get("is_automated_address"), row.get("data_quality_status"), "; ".join(row.get("validation_messages") or []), row.get("import_action")])
        return output.getvalue().encode("utf-8")

    def row_payload(self, row: ImportRow, issues: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        data = dict(row.normalized_data or {})
        if issues is None:
            issues = [
                {
                    "field_name": item.field_name,
                    "raw_value": item.raw_value,
                    "error_code": item.error_code,
                    "error_message": item.error_message,
                    "severity": item.severity,
                }
                for item in self.db.query(DataValidationError).filter_by(import_row_id=row.id).all()
            ]
        data.update({
            "import_row_id": row.id,
            "row_number": row.row_number,
            "import_status": row.processing_status,
            "validation_messages": [item.get("error_message") for item in issues],
            "issues": issues,
        })
        return data

    def metrics(self, rows: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "contacts": sum(1 for row in rows if row.get("email")),
            "skipped_group_rows": sum(1 for row in rows if row.get("import_status") == "skipped"),
            "invalid_rows": sum(1 for row in rows if row.get("import_status") == "error"),
            "duplicates": sum(1 for row in rows if row.get("existing_contact_id")),
            "needs_organization_match": sum(1 for row in rows if row.get("data_quality_status") == "needs_organization_match"),
            "missing_role": sum(1 for row in rows if not row.get("role_title") and row.get("email")),
            "missing_phone": sum(1 for row in rows if not row.get("phone") and row.get("email")),
            "shared_inboxes": sum(1 for row in rows if row.get("is_shared_inbox")),
            "automated_addresses": sum(1 for row in rows if row.get("is_automated_address")),
            "high_engagement": sum(1 for row in rows if row.get("engagement_level") == "high"),
        }

    def match_organization(self, domain: str) -> dict[str, Any]:
        if not domain or domain in PUBLIC_DOMAINS:
            return {}
        mapping = self.db.query(erp.OrganizationDomainMapping).filter(func.lower(erp.OrganizationDomainMapping.domain) == domain, erp.OrganizationDomainMapping.status == "approved").first()
        if mapping:
            return self._org_payload(mapping.organization_type, mapping.organization_id)
        for client in self.db.query(erp.Client).all():
            if self._domain_matches_name(domain, client.name):
                return {"organization_type": "client", "client_id": client.id, "name": client.name}
        for manufacturer in self.db.query(Manufacturer).all():
            if self._domain_matches_name(domain, manufacturer.name) or domain in str(manufacturer.website or "").casefold():
                return {"organization_type": "manufacturer", "manufacturer_id": manufacturer.id, "name": manufacturer.name}
        for supplier in self.db.query(Supplier).all():
            if self._domain_matches_name(domain, supplier.name) or domain in str(supplier.website or "").casefold():
                return {"organization_type": "supplier", "supplier_id": supplier.id, "name": supplier.name}
        return {}

    def _org_payload(self, organization_type: str, organization_id: int) -> dict[str, Any]:
        if organization_type == "client":
            row = self.db.get(erp.Client, organization_id)
            return {"organization_type": "client", "client_id": organization_id, "name": row.name if row else None}
        if organization_type == "manufacturer":
            row = self.db.get(Manufacturer, organization_id)
            return {"organization_type": "manufacturer", "manufacturer_id": organization_id, "name": row.name if row else None}
        if organization_type == "supplier":
            row = self.db.get(Supplier, organization_id)
            return {"organization_type": "supplier", "supplier_id": organization_id, "name": row.name if row else None}
        return {"organization_type": organization_type, "name": None}

    def _domain_matches_name(self, domain: str, name: str) -> bool:
        stem = domain.split(".", 1)[0].replace("-", "").replace("_", "")
        normalized_name = re.sub(r"[^a-z0-9]", "", name.casefold())
        return len(stem) >= 4 and (stem in normalized_name or normalized_name in stem)

    def find_existing(self, normalized_email: str) -> erp.Contact | None:
        return self.db.query(erp.Contact).filter(or_(func.lower(erp.Contact.normalized_email) == normalized_email, func.lower(erp.Contact.email) == normalized_email)).first()

    def apply_decision(self, data: dict[str, Any], decision: dict[str, Any]) -> None:
        if not decision:
            return
        if decision.get("organization_type"):
            data["organization_type"] = decision["organization_type"]
        for field in ("client_id", "manufacturer_id", "supplier_id", "client_site_id"):
            if decision.get(field) is not None:
                data[field] = decision[field]
        if decision.get("organization_type") == "personal":
            data["client_id"] = data["manufacturer_id"] = data["supplier_id"] = None
        if decision.get("data_quality_status"):
            data["data_quality_status"] = decision["data_quality_status"]

    def issue(self, row_number: int, field: str, raw_value: Any, code: str, message: str, severity: str) -> dict[str, Any]:
        return {"row_number": row_number, "field_name": field, "raw_value": str(raw_value or ""), "error_code": code, "error_message": message, "severity": severity}

    def _audit(self, event_type: str, entity_type: str, entity_id: str | None, values: dict[str, Any]) -> None:
        self.db.add(AuditEvent(event_type=event_type, entity_type=entity_type, entity_id=entity_id, user_id=self.user_id, source=SOURCE, new_values=values))
