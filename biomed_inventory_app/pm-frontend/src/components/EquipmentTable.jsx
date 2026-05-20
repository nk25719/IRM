import React from "react";

export default function EquipmentTable({
  rows,
  getTrackingMeta,
  badgeClass,
  getPmSlotStatus,
}) {
  return (
    <div className="card">
      <h2 className="section-title">Equipment List</h2>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Hospital</th>
              <th>Equipment</th>
              <th>Model</th>
              <th>Department</th>
              <th>Frequency</th>
              <th>Next PM</th>
              <th>Last PM</th>
              <th>Completion</th>
              <th>PM1</th>
              <th>PM2</th>
              <th>PM3</th>
              <th>Engineer</th>
              <th>Reminders</th>
              <th>Due-soon Flags</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const meta = getTrackingMeta(row);
              return (
                <tr key={row.id}>
                  <td>{row.hospital}</td>
                  <td>
                    <div className="strong">{row.equipment}</div>
                    <div className="muted">{row.serial}</div>
                  </td>
                  <td>{row.model}</td>
                  <td>{row.department || "—"}</td>
                  <td>
                    <div>{row.pmsPerYear} PM/year</div>
                    <div className="muted">{meta.intervalMonths} month interval</div>
                  </td>
                  <td>
                    <div>{row.nextPmDate}</div>
                    <div className="muted">{meta.daysUntil} days</div>
                  </td>
                  <td>{row.lastPmDate || "—"}</td>
                  <td>{row.completionDate || "—"}</td>
                  <td>{getPmSlotStatus(row, 1)}</td>
                  <td>{getPmSlotStatus(row, 2)}</td>
                  <td>{getPmSlotStatus(row, 3)}</td>
                  <td>{row.engineer}</td>
                  <td className="muted">
                    <div>R1: {row.reminder1Sent ? "Sent" : "Pending"}</div>
                    <div>R2: {row.reminder2Sent ? "Sent" : "Pending"}</div>
                    <div>Alert: {row.engineerAlertSent ? "Sent" : "Pending"}</div>
                  </td>
                  <td className="muted">
                    {meta.isOverdue
                      ? "Overdue"
                      : meta.dueSoon7
                        ? "Due within 7 days"
                        : meta.dueSoon14
                          ? "Due within 14 days"
                          : "Not due soon"}
                  </td>
                  <td>
                    <span className={badgeClass(row.status, meta)}>{meta.effectiveStatus}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
