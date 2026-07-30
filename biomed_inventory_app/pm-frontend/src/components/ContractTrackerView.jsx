import React, { useMemo, useState } from "react";
import { AlertTriangle, BarChart3, CheckCircle2, Download, FileCog, FileText, FileUp, MoreHorizontal, PlusCircle, Wrench } from "lucide-react";

function getContractTimingLabel(daysLeft) {
  if (daysLeft < 0) return { label: `Expired ${Math.abs(daysLeft)} day(s) ago`, className: "badge badge-overdue" };
  if (daysLeft <= 30) return { label: `Renew within ${daysLeft} day(s)`, className: "badge badge-due-soon" };
  return { label: `${daysLeft} day(s) remaining`, className: "badge badge-confirmed" };
}

export default function ContractTrackerView({
  contracts,
  onOpenContract,
  contractFileInputRef,
  onImportContracts,
  onExportContractsCsv,
  onOpenHospitalStatus,
  isAddEquipmentVisible,
  onToggleAddEquipment,
  addEquipmentPanel,
}) {
  const [activeTab, setActiveTab] = useState("all");
  const contractGroups = useMemo(() => {
    const renewal = contracts.filter((contract) => Number(contract.daysLeft) <= 30);
    const active = contracts.filter((contract) => Number(contract.daysLeft) > 30);
    const equipment = contracts.flatMap((contract) =>
      (contract.equipment || []).map((item) => ({
        contractId: contract.id,
        hospital: contract.hospital,
        contractNo: contract.contractNo,
        equipment: item,
        contractEndDate: contract.contractEndDate,
        daysLeft: contract.daysLeft,
      }))
    );
    return { all: contracts, renewal, active, equipment };
  }, [contracts]);

  const tabs = [
    { id: "all", label: "All", count: contractGroups.all.length, icon: FileText },
    { id: "renewal", label: "Renewals", count: contractGroups.renewal.length, icon: AlertTriangle },
    { id: "active", label: "Active", count: contractGroups.active.length, icon: CheckCircle2 },
    { id: "equipment", label: "Equipment", count: contractGroups.equipment.length, icon: Wrench },
  ];
  const visibleContracts = activeTab === "renewal" ? contractGroups.renewal : activeTab === "active" ? contractGroups.active : contractGroups.all;

  return (
    <div className="card contracts-view-card">
      <div className="contracts-toolbar">
        <div className="actions actions-friendly">
          <a className="button button-primary" href="/aftersales/preventivemaintenance" aria-label="Manage Contracts">
            <FileCog size={15} className="inline-icon" />
            Manage Contracts
          </a>
          <button className="button button-soft" onClick={onOpenHospitalStatus} aria-label="Open Hospital Contract Status">
            <BarChart3 size={15} className="inline-icon" />
            Hospital Contract Status
          </button>
          <button className="button button-primary" onClick={onToggleAddEquipment}>
            <PlusCircle size={15} className="inline-icon" />
            {isAddEquipmentVisible ? "Hide add equipment" : "Add equipment"}
          </button>
          <details className="utility-menu">
            <summary aria-label="Contract utilities">
              <MoreHorizontal size={18} />
            </summary>
            <div className="utility-popover">
              <input
                ref={contractFileInputRef}
                type="file"
                accept=".csv,.xlsx,.xls"
                className="hidden-input"
                onChange={onImportContracts}
              />
              <button type="button" onClick={() => contractFileInputRef?.current?.click()}>
                <FileUp size={15} className="inline-icon" />
                Import contracts
              </button>
              <button type="button" onClick={onExportContractsCsv}>
                <Download size={15} className="inline-icon" />
                Export contracts
              </button>
            </div>
          </details>
        </div>
      </div>

      {isAddEquipmentVisible ? addEquipmentPanel : null}

      <div className="contract-tabs" role="tablist" aria-label="Contract views">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              className={`contract-tab ${activeTab === tab.id ? "contract-tab-active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <Icon size={15} className="inline-icon" />
              <span>{tab.label}</span>
              <b>{tab.count}</b>
            </button>
          );
        })}
      </div>

      {activeTab === "equipment" ? (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Equipment</th>
                <th>Hospital</th>
                <th>Contract #</th>
                <th>Contract end</th>
                <th>Expiration</th>
              </tr>
            </thead>
            <tbody>
              {contractGroups.equipment.length ? (
                contractGroups.equipment.map((item) => {
                  const timing = getContractTimingLabel(item.daysLeft);
                  return (
                    <tr key={`${item.contractId}-${item.equipment}`}>
                      <td className="strong">{item.equipment || "Unnamed equipment"}</td>
                      <td className="muted">{item.hospital || "—"}</td>
                      <td>
                        <button className="button button-soft" onClick={() => onOpenContract(item.contractId)}>
                          {item.contractNo || "View contract"}
                        </button>
                      </td>
                      <td className="muted">{item.contractEndDate || "—"}</td>
                      <td>
                        <span className={timing.className}>{timing.label}</span>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={5} className="empty-state empty-state-compact">
                    No equipment linked to contracts yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      ) : (
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
              {visibleContracts.length ? (
                visibleContracts.map((contract) => {
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
                  <td colSpan={5} className="empty-state empty-state-compact">
                    No contracts found in this view.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
