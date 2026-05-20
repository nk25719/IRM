# PM Tracker Market Research and Feature Additions (Healthcare/Biomed)

## High-value additions commonly seen in mature PM tools

1. **Regulatory readiness and audit traceability**
   - Full timestamped log of status changes, emails, approvals, and technician actions.
   - Exportable audit report per hospital, contract, and equipment.

2. **Communication-centric workflow (COM timeline)**
   - Threaded notes and comments by user.
   - Email history and response tracking.
   - “Awaiting hospital response” state and SLA timers.

3. **Contract + SLA risk layer**
   - Contract expiry early-warning (90/60/30 day reminders).
   - SLA breach risk based on due date + hospital response delays.

4. **Work-order and engineer utilization planning**
   - Route-ready scheduling by location/hospital.
   - Technician workload balancing and assignment scoring.

5. **Parts/consumables and service blockers**
   - PM blocked reason tracking (spares unavailable, access denied, etc.).
   - Spare part ETA and linked procurement notes.

6. **Document attachments per equipment**
   - Last PM certificate, calibration document, and signed service report.

7. **Executive dashboard**
   - Compliance %, overdue trend, first-time-fix rate, contract renewal risk.

## Recommended next additions for this project

- Add role-based profiles (Admin, PM Coordinator, Engineer).
- Add “Awaiting Hospital”, “Blocked”, and “Escalated” status subsets.
- Add email template library per hospital.
- Add response-tracking fields (`lastReplyAt`, `followUpCount`).
- Add printable hospital weekly report.
