import React from "react";

export default function EquipmentDetailModal({ row, onClose }) {
  if (!row) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" onClick={(event) => event.stopPropagation()}>
        <div className="detail-head">
          <h2 className="section-title">Equipment Detail</h2>
          <button className="button" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="detail-grid">
          <div><span className="strong">Hospital:</span> {row.hospital || "—"}</div>
          <div><span className="strong">Contract:</span> {row.contractNo || "—"}</div>
          <div><span className="strong">Equipment:</span> {row.equipment || "—"}</div>
          <div><span className="strong">Model:</span> {row.model || "—"}</div>
          <div><span className="strong">Serial:</span> {row.serial || "—"}</div>
          <div><span className="strong">Department:</span> {row.department || "—"}</div>
          <div><span className="strong">PM Frequency:</span> {row.pmsPerYear || 1}/year</div>
          <div><span className="strong">Next PM:</span> {row.nextPmDate || "—"}</div>
          <div><span className="strong">Last PM:</span> {row.lastPmDate || "—"}</div>
          <div><span className="strong">Engineer:</span> {row.engineer || "—"}</div>
        </div>

        <div className="audit-grid">
          <div className="strong">Audit Trail</div>
          <div className="muted">Created: {row.createdDate || "—"}</div>
          <div className="muted">Updated: {row.updatedDate || "—"}</div>
          <div className="muted">Updated By: {row.updatedBy || "System"}</div>
        </div>

        <div>
          <div className="strong">PM History</div>
          <div className="history-list">
            {(row.pmHistory || []).length ? (
              row.pmHistory.map((entry, index) => (
                <div key={`${entry.date || "pm"}-${index}`} className="history-item">
                  <div className="strong">{entry.date || "Unknown date"}</div>
                  <div className="muted">Status: {entry.status || "Completed"}</div>
                  <div className="muted">By: {entry.updatedBy || "System"}</div>
                  {entry.notes ? <div className="muted">{entry.notes}</div> : null}
                </div>
              ))
            ) : (
              <div className="muted">No PM history yet.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
