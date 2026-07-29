# Customer Contacts Import

The Customer Contacts importer stages the Outlook-derived workbook
`Customer_Contacts-2.xlsx` into the existing IRM CRM and Data Management Center
foundation. This source is Outlook email history, not the Outlook People or
Contacts directory.

## Workflow

1. Open `/crm/contacts`.
2. Upload the workbook on the Customer Contacts Import panel.
3. Preview the staged rows before changing CRM data.
4. Review validation warnings, duplicates, shared inboxes, automated addresses,
   public domains, and unmatched organization domains.
5. Confirm reviewed rows.
6. Download the CSV import report.

Preview writes only to `import_batches`, `import_rows`, and
`data_validation_errors`. Contacts are created or updated only during confirm.

## Workbook Rules

The importer defaults to the `Customer Contacts` worksheet and expects:

- `Name`
- `Email`
- `Company / Domain`
- `Emails Exchanged`
- `Role`
- `Phone`
- `Notes`

Rows with a blank `Email` are treated as domain/group headings and are skipped,
not imported as contacts.

Email is normalized to lowercase and stored as `normalized_email`, which is the
deduplication key. The email-derived domain is stored in `email_domain`; if the
workbook domain disagrees, the row receives a warning and the email-derived
domain wins.

## Organization Matching

The importer checks approved `organization_domain_mappings` first, then attempts
case-insensitive matches to existing clients, manufacturers, and suppliers. It
does not create organizations automatically.

Public email domains such as `gmail.com`, `hotmail.com`, `outlook.com`,
`yahoo.com`, `live.com`, and `icloud.com` are marked as personal/review contacts
and are not linked to fake organizations.

## Engagement and Quality

`Emails Exchanged` is stored as a non-negative integer and mapped to:

- `low`: 0-2
- `moderate`: 3-9
- `active`: 10-29
- `high`: 30+

This is only an approximate activity indicator. It is not a count of distinct
conversations and does not represent last-contact date.

Phone extraction is best effort. Imported phone numbers are unverified and do
not overwrite a verified existing phone number. Blank roles are kept blank and
set quality status to `needs_role` unless a stronger review issue exists.

## Review Flags

The importer detects shared inboxes such as purchasing, procurement, service,
support, sales, finance, training, biomedical, and clinical engineering.

It also flags automated/system addresses such as noreply, notifications,
mailer-daemon, account-security, learning.notifications, automated, and system.
These are visible in the review screen and can be rejected or retained.

## APIs

- `POST /api/imports/customer-contacts/preview`
- `POST /api/imports/customer-contacts/confirm`
- `GET /api/imports/customer-contacts/{import_id}`
- `GET /api/imports/customer-contacts/{import_id}/report`
- `GET /api/contacts`
- `GET /api/contacts/{contact_id}`
- `POST /api/contacts`
- `PATCH /api/contacts/{contact_id}`
- `POST /api/contacts/bulk-organization-match`

Import and bulk organization matching require a CRM/admin-style manage role.
Contact views avoid exposing restricted pricing, invoices, or sales financial
details.
