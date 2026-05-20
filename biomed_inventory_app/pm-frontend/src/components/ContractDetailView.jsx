import React from "react";
import { ArrowLeft, FileText, PlusCircle, Trash2 } from "lucide-react";

export default function ContractDetailView({
  contract,
  contractRows,
  addEquipmentDraft,
  onAddEquipmentDraftChange,
  onAddEquipmentToContract,
  onRemoveEquipmentFromContract,
  onBack,
}) {
  if (!contract) return null;

  function handleSubmit(event) {
    event.preventDefault();
    onAddEquipmentToContract(contract.id, addEquipmentDraft);
  }

  return (
    <div className="card contracts-view-card">
      <div className="detail-head">
        <div>
          <h2 className="section-title">Contract Details</h2>
          <div className="hospital-headline">
            <FileText size={16} className="inline-icon" />
            {contract.hospital || "Unknown hospital"} · {contract.contractNo || "No contract #"}
          </div>
        </div>
        <button className="button" onClick={onBack}>
          <ArrowLeft size={15} className="inline-icon" />
          Back to contracts
        </button>
      </div>

      <div className="bulk-preview">
        <div className="strong">Contract period</div>
        <div className="muted">
          {contract.contractStartDate || "—"} to {contract.contractEndDate || "—"}
        </div>
      </div>

      <div className="bulk-preview">
        <div className="strong">Included equipment ({contract.equipment?.length || 0})</div>
        {contractRows?.length ? (
          <div className="bulk-preview-list">
            {contractRows.map((row) => (
              <div key={row.id} className="bulk-preview-item">
                <div className="strong">{row.equipment || "Unnamed equipment"}</div>
                <div className="muted">
                  Serial: {row.serial || "—"} · Model: {row.model || "—"} · Dept: {row.department || "—"}
                </div>
                <div className="muted">
                  PM/year: {row.pmsPerYear || "—"} · Next PM: {row.nextPmDate || "—"}
                </div>
                <button className="button button-soft" onClick={() => onRemoveEquipmentFromContract(row.id)}>
                  <Trash2 size={14} className="inline-icon" />
                  Remove from contract
                </button>
              </div>
            ))}
          </div>
        ) : (
          <div className="muted">No equipment linked to this contract yet.</div>
        )}
      </div>

      <div className="card form-card">
        <div className="form-head">
          <h2 className="section-title">Add Equipment to this Contract</h2>
        </div>
        <form className="equipment-form" onSubmit={handleSubmit}>
          <div className="form-grid">
            <input
              required
              className="input"
              placeholder="Equipment"
              value={addEquipmentDraft.equipment}
              onChange={(event) => onAddEquipmentDraftChange("equipment", event.target.value)}
            />
            <input
              className="input"
              placeholder="Serial"
              value={addEquipmentDraft.serial}
              onChange={(event) => onAddEquipmentDraftChange("serial", event.target.value)}
            />
            <input
              className="input"
              placeholder="Model"
              value={addEquipmentDraft.model}
              onChange={(event) => onAddEquipmentDraftChange("model", event.target.value)}
            />
            <input
              className="input"
              placeholder="Department"
              value={addEquipmentDraft.department}
              onChange={(event) => onAddEquipmentDraftChange("department", event.target.value)}
            />
            <input
              className="input"
              type="number"
              min="1"
              placeholder="PMs per Year"
              value={addEquipmentDraft.pmsPerYear}
              onChange={(event) => onAddEquipmentDraftChange("pmsPerYear", event.target.value)}
            />
            <input
              className="input"
              type="date"
              value={addEquipmentDraft.nextPmDate}
              onChange={(event) => onAddEquipmentDraftChange("nextPmDate", event.target.value)}
            />
          </div>
          <button className="button button-primary" type="submit">
            <PlusCircle size={15} className="inline-icon" />
            Add equipment to contract
          </button>
        </form>
      </div>
    </div>
  );
}
