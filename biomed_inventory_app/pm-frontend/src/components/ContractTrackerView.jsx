import React from "react";
import { ArrowLeft, FileText } from "lucide-react";

function getContractTimingLabel(daysLeft) {
  if (daysLeft < 0) return { label: `Expired ${Math.abs(daysLeft)} day(s) ago`, className: "badge badge-overdue" };
  if (daysLeft <= 30) return { label: `Renew within ${daysLeft} day(s)`, className: "badge badge-due-soon" };
  return { label: `${daysLeft} day(s) remaining`, className: "badge badge-confirmed" };
}

export default function ContractTrackerView({
  contracts,
  onOpenContract,
}) {
  return (
    <div className="card contracts-view-card">
      <div className="detail-head">
        <div>
          <h2 className="section-title">Hospital Contracts</h2>
          <div className="hospital-headline">
            <FileText size={16} className="inline-icon" />
            Independent contract tracker with renewal reminders
          </div>
        </div>
      </div>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Hospital</th>
              <th>Contract #</th>
              <th>Contract period</th>
              <th>Equipment</th>
              <th>Expiration</th>
            </tr>
          </thead>
          <tbody>
            {contracts.length ? (
              contracts.map((contract) => {
                const timing = getContractTimingLabel(contract.daysLeft);
                return (
                  <tr key={contract.id}>
                    <td className="strong">{contract.hospital || "—"}</td>
                    <td>
                      <button className="button button-soft" onClick={() => onOpenContract(contract.id)}>
                        {contract.contractNo || "View contract"}
                      </button>
                    </td>
                    <td className="muted">
                      {contract.contractStartDate || "—"} to {contract.contractEndDate || "—"}
                    </td>
                    <td className="muted">
                      {contract.equipment?.length
                        ? `${contract.equipment.length} item(s) linked`
                        : "No equipment linked yet"}
                    </td>
                    <td>
                      <span className={timing.className}>{timing.label}</span>
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={5} className="muted">
                  No contracts found yet. Add contract start/end dates in equipment records to populate this view.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
