import React, { useMemo, useState } from "react";
import {
  ArrowLeft,
  Building2,
  CheckCircle2,
  Download,
  FileText,
  MoreHorizontal,
  RefreshCw,
  Search,
  ShieldCheck,
  Stethoscope,
  Wrench,
} from "lucide-react";
import { getDaysUntil } from "../utils/dateUtils";

const INACTIVE_CONTRACT_STATUSES = new Set(["cancelled", "canceled", "suspended", "inactive", "void"]);

function csvCell(value) {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

function getContractState(contract) {
  if (!contract?.contractNo) return "No Active Contract";
  const rawStatus = String(contract.status || "").trim().toLowerCase();
  if (INACTIVE_CONTRACT_STATUSES.has(rawStatus)) return "Suspended";
  const daysLeft = Number.isFinite(contract.daysLeft) ? contract.daysLeft : getDaysUntil(contract.contractEndDate);
  if (daysLeft < 0) return "Expired";
  if (daysLeft <= 90) return "Expiring Soon";
  return "Active";
}

function statusBadgeClass(status) {
  if (status === "Active") return "badge badge-confirmed";
  if (status === "Expiring Soon") return "badge badge-due-soon";
  if (status === "Expired" || status === "No Active Contract") return "badge badge-overdue";
  return "badge badge-default";
}

function getNextAction(row) {
  if (row.contractStatus === "Expired") return "Prepare renewal quotation";
  if (row.contractStatus === "Expiring Soon") return "Start renewal review";
  if (row.contractStatus === "No Active Contract") return row.installedEquipmentCount ? "Contact hospital" : "Complete contract data";
  if (row.uncoveredEquipmentCount > 0) return "Add uncovered equipment to contract";
  if (row.pmVisitsRequired > row.pmVisitsCompleted) return "Schedule overdue PM";
  if (!row.laborIncluded) return "Review labor coverage";
  if (!row.contractStartDate || !row.contractEndDate) return "Verify contract dates";
  return "No immediate action";
}

function buildHospitalRows(rows, contracts) {
  const hospitalMap = new Map();
  rows.forEach((row) => {
    const hospital = row.hospital || "Not recorded";
    if (!hospitalMap.has(hospital)) {
      hospitalMap.set(hospital, {
        clientName: hospital,
        siteName: "Not recorded",
        installedRows: [],
        contracts: [],
      });
    }
    hospitalMap.get(hospital).installedRows.push(row);
  });

  contracts.forEach((contract) => {
    const hospital = contract.hospital || "Not recorded";
    if (!hospitalMap.has(hospital)) {
      hospitalMap.set(hospital, {
        clientName: hospital,
        siteName: "Not recorded",
        installedRows: [],
        contracts: [],
      });
    }
    hospitalMap.get(hospital).contracts.push(contract);
  });

  return Array.from(hospitalMap.values()).map((bucket) => {
    const activeContracts = bucket.contracts
      .filter((contract) => ["Active", "Expiring Soon"].includes(getContractState(contract)))
      .sort((a, b) => getDaysUntil(a.contractEndDate) - getDaysUntil(b.contractEndDate));
    const primaryContract = activeContracts[0] || bucket.contracts.sort((a, b) => getDaysUntil(a.contractEndDate) - getDaysUntil(b.contractEndDate))[0] || null;
    const contractStatus = getContractState(primaryContract);
    const installedEquipmentCount = bucket.installedRows.length;
    const contractedEquipmentNames = new Set(activeContracts.flatMap((contract) => contract.equipment || []));
    const contractedEquipmentCount = Math.min(installedEquipmentCount, contractedEquipmentNames.size || (primaryContract ? primaryContract.equipment?.length || 0 : 0));
    const uncoveredEquipmentCount = Math.max(0, installedEquipmentCount - contractedEquipmentCount);
    const pmVisitsRequired = bucket.installedRows.reduce((sum, row) => sum + Math.max(1, Number(row.pmsPerYear) || 1), 0);
    const pmVisitsCompleted = bucket.installedRows.reduce((sum, row) => sum + (row.pmHistory || []).filter((entry) => entry.status === "Completed").length, 0);
    const laborIncluded = bucket.installedRows.some((row) => ["true", "yes", "included"].includes(String(row.laborIncluded || "").toLowerCase()));
    const row = {
      clientName: bucket.clientName,
      siteName: bucket.siteName,
      activeContractId: primaryContract?.id || "",
      activeContractNumber: primaryContract?.contractNo || "Not recorded",
      activeContractType: primaryContract?.contractNo ? "Customer Service Contract" : "Not recorded",
      contractStartDate: primaryContract?.contractStartDate || "",
      contractEndDate: primaryContract?.contractEndDate || "",
      daysUntilExpiry: primaryContract?.contractEndDate ? getDaysUntil(primaryContract.contractEndDate) : null,
      contractStatus,
      installedEquipmentCount,
      contractedEquipmentCount,
      uncoveredEquipmentCount,
      coveragePercentage: installedEquipmentCount ? Math.round((contractedEquipmentCount / installedEquipmentCount) * 100) : 0,
      pmIncluded: pmVisitsRequired > 0,
      laborIncluded,
      pmVisitsRequired,
      pmVisitsCompleted,
      renewalStatus: contractStatus === "Expiring Soon" ? "Renewal in Progress" : contractStatus,
      accountOwner: bucket.installedRows.find((rowItem) => rowItem.engineer)?.engineer || "Not recorded",
    };
    row.recommendedNextAction = getNextAction(row);
    row.uncoveredEquipment = bucket.installedRows
      .filter((equipmentRow) => !Array.from(contractedEquipmentNames).some((name) => name.includes(equipmentRow.serial) || name.includes(equipmentRow.equipment)))
      .map((equipmentRow) => [equipmentRow.equipment, equipmentRow.model, equipmentRow.serial].filter(Boolean).join(" / "));
    return row;
  });
}

function defaultSort(a, b) {
  const rank = { Expired: 0, "Expiring Soon": 1, "No Active Contract": 2, Active: 3 };
  const statusDiff = (rank[a.contractStatus] ?? 4) - (rank[b.contractStatus] ?? 4);
  if (statusDiff !== 0) return statusDiff;
  if (b.uncoveredEquipmentCount !== a.uncoveredEquipmentCount) return b.uncoveredEquipmentCount - a.uncoveredEquipmentCount;
  return a.clientName.localeCompare(b.clientName);
}

export default function HospitalContractStatusView({
  rows,
  contracts,
  onBackToContracts,
  onOpenContract,
  onRefresh,
  lastRefreshed,
}) {
  const [filters, setFilters] = useState({
    search: "",
    status: "All",
    type: "All",
    expiry: "All",
    active: "All",
    uncovered: "All",
    pm: "All",
    labor: "All",
    coverage: "",
    owner: "All",
  });
  const [expandedHospital, setExpandedHospital] = useState("");

  const hospitalRows = useMemo(() => buildHospitalRows(rows, contracts), [rows, contracts]);
  const owners = useMemo(() => ["All", ...Array.from(new Set(hospitalRows.map((row) => row.accountOwner).filter((owner) => owner && owner !== "Not recorded")))], [hospitalRows]);

  const visibleRows = useMemo(() => {
    const searchTerm = filters.search.trim().toLowerCase();
    return hospitalRows
      .filter((row) => {
        const matchesSearch =
          !searchTerm ||
          [
            row.clientName,
            row.siteName,
            row.activeContractNumber,
            row.activeContractType,
            row.uncoveredEquipment.join(" "),
          ]
            .join(" ")
            .toLowerCase()
            .includes(searchTerm);
        const matchesStatus = filters.status === "All" || row.contractStatus === filters.status;
        const matchesType = filters.type === "All" || row.activeContractType === filters.type;
        const matchesExpiry =
          filters.expiry === "All" ||
          (filters.expiry === "30" && row.daysUntilExpiry !== null && row.daysUntilExpiry >= 0 && row.daysUntilExpiry <= 30) ||
          (filters.expiry === "60" && row.daysUntilExpiry !== null && row.daysUntilExpiry >= 0 && row.daysUntilExpiry <= 60) ||
          (filters.expiry === "90" && row.daysUntilExpiry !== null && row.daysUntilExpiry >= 0 && row.daysUntilExpiry <= 90) ||
          (filters.expiry === "180" && row.daysUntilExpiry !== null && row.daysUntilExpiry >= 0 && row.daysUntilExpiry <= 180);
        const matchesActive = filters.active === "All" || (filters.active === "Yes" ? row.contractStatus === "Active" || row.contractStatus === "Expiring Soon" : row.contractStatus !== "Active" && row.contractStatus !== "Expiring Soon");
        const matchesUncovered = filters.uncovered === "All" || (filters.uncovered === "Yes" ? row.uncoveredEquipmentCount > 0 : row.uncoveredEquipmentCount === 0);
        const matchesPm = filters.pm === "All" || (filters.pm === "Yes" ? row.pmIncluded : !row.pmIncluded);
        const matchesLabor = filters.labor === "All" || (filters.labor === "Yes" ? row.laborIncluded : !row.laborIncluded);
        const matchesCoverage = !filters.coverage || row.coveragePercentage >= Number(filters.coverage);
        const matchesOwner = filters.owner === "All" || row.accountOwner === filters.owner;
        return matchesSearch && matchesStatus && matchesType && matchesExpiry && matchesActive && matchesUncovered && matchesPm && matchesLabor && matchesCoverage && matchesOwner;
      })
      .sort(defaultSort);
  }, [filters, hospitalRows]);

  const summary = useMemo(() => {
    const totalInstalled = hospitalRows.reduce((sum, row) => sum + row.installedEquipmentCount, 0);
    const totalContracted = hospitalRows.reduce((sum, row) => sum + row.contractedEquipmentCount, 0);
    return {
      totalHospitals: hospitalRows.length,
      activeHospitals: hospitalRows.filter((row) => row.contractStatus === "Active" || row.contractStatus === "Expiring Soon").length,
      noActiveHospitals: hospitalRows.filter((row) => row.contractStatus === "No Active Contract").length,
      expiring90: hospitalRows.filter((row) => row.daysUntilExpiry !== null && row.daysUntilExpiry >= 0 && row.daysUntilExpiry <= 90).length,
      expired: hospitalRows.filter((row) => row.contractStatus === "Expired").length,
      totalInstalled,
      totalContracted,
      uncovered: hospitalRows.reduce((sum, row) => sum + row.uncoveredEquipmentCount, 0),
      coverage: totalInstalled ? Math.round((totalContracted / totalInstalled) * 100) : 0,
    };
  }, [hospitalRows]);

  function updateFilter(field, value) {
    setFilters((current) => ({ ...current, [field]: value }));
  }

  function clearFilters() {
    setFilters({ search: "", status: "All", type: "All", expiry: "All", active: "All", uncovered: "All", pm: "All", labor: "All", coverage: "", owner: "All" });
  }

  function exportVisibleRows() {
    const headers = [
      "Hospital",
      "Site",
      "Contract number",
      "Contract type",
      "Contract status",
      "Start date",
      "End date",
      "Days until expiry",
      "Installed equipment",
      "Contracted equipment",
      "Uncovered equipment",
      "Coverage percentage",
      "PM included",
      "Labor included",
      "PM visits required",
      "PM visits completed",
      "Renewal status",
      "Owner",
      "Recommended next action",
    ];
    const csv = [headers.join(",")]
      .concat(
        visibleRows.map((row) =>
          [
            row.clientName,
            row.siteName,
            row.activeContractNumber,
            row.activeContractType,
            row.contractStatus,
            row.contractStartDate,
            row.contractEndDate,
            row.daysUntilExpiry ?? "Not recorded",
            row.installedEquipmentCount,
            row.contractedEquipmentCount,
            row.uncoveredEquipmentCount,
            `${row.coveragePercentage}%`,
            row.pmIncluded ? "Yes" : "No",
            row.laborIncluded ? "Yes" : "No",
            row.pmVisitsRequired,
            row.pmVisitsCompleted,
            row.renewalStatus,
            row.accountOwner,
            row.recommendedNextAction,
          ].map(csvCell).join(",")
        )
      )
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "hospital-contract-status.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  const kpis = [
    ["Total Hospitals", summary.totalHospitals, "Customer accounts with installed equipment or contracts.", Building2, () => clearFilters()],
    ["Hospitals with Active Contracts", summary.activeHospitals, "Active or expiring customer contracts.", CheckCircle2, () => updateFilter("active", "Yes")],
    ["Hospitals without Active Contracts", summary.noActiveHospitals, "Hospitals needing customer contract follow-up.", ShieldCheck, () => updateFilter("active", "No")],
    ["Contracts Expiring within 90 Days", summary.expiring90, "Customer contracts ending soon.", FileText, () => updateFilter("expiry", "90")],
    ["Expired Contracts", summary.expired, "Contracts past end date.", FileText, () => updateFilter("status", "Expired")],
    ["Total Installed Equipment", summary.totalInstalled, "Installed equipment counted by hospital.", Wrench, () => clearFilters()],
    ["Customer-Contracted Equipment", summary.totalContracted, "Equipment included in customer service contracts.", Stethoscope, () => updateFilter("active", "Yes")],
    ["Uncovered Equipment", summary.uncovered, "Installed equipment not linked to active customer contracts.", ShieldCheck, () => updateFilter("uncovered", "Yes")],
    ["Overall Contract Coverage %", `${summary.coverage}%`, "Customer-contracted equipment over installed equipment.", CheckCircle2, () => clearFilters()],
  ];

  return (
    <div className="hospital-contract-status">
      <section className="hospital-status-header">
        <div>
          <div className="breadcrumbs">After Sales / Contracts / Hospital Contract Status</div>
          <h2 className="section-title">Hospital Contract Status</h2>
          <p className="muted">Review customer service contract coverage, expiration risk, and renewal opportunities by hospital.</p>
          <p className="muted">Last refreshed: {lastRefreshed || "Not recorded"}</p>
        </div>
        <div className="actions actions-friendly">
          <button className="button button-soft" onClick={onBackToContracts}>
            <ArrowLeft size={15} className="inline-icon" />
            Back to Contracts
          </button>
          <button className="button button-soft" onClick={onBackToContracts}>
            <FileText size={15} className="inline-icon" />
            View Contracts
          </button>
          <button className="button button-soft" onClick={onRefresh}>
            <RefreshCw size={15} className="inline-icon" />
            Refresh
          </button>
          <details className="utility-menu">
            <summary aria-label="Hospital status utilities">
              <MoreHorizontal size={18} />
            </summary>
            <div className="utility-popover">
              <button type="button" onClick={exportVisibleRows}>
                <Download size={15} className="inline-icon" />
                Export visible rows
              </button>
            </div>
          </details>
        </div>
      </section>

      <section className="hospital-status-kpis">
        {kpis.map(([label, value, help, Icon, onClick]) => (
          <button key={label} className="card metric-card-button hospital-status-kpi" onClick={onClick}>
            <div className="metric-row">
              <div>
                <div className="metric-label">{label}</div>
                <div className="metric-value">{value}</div>
                <div className="muted">{help}</div>
              </div>
              <Icon size={20} aria-hidden="true" />
            </div>
          </button>
        ))}
      </section>

      <section className="card hospital-status-filters">
        <div className="hospital-status-filter-grid">
          <div className="search-wrap">
            <Search size={16} className="search-icon" />
            <input className="input search-input" value={filters.search} onChange={(event) => updateFilter("search", event.target.value)} placeholder="Search hospital, site, contract, model, serial" />
          </div>
          <select className="select" value={filters.status} onChange={(event) => updateFilter("status", event.target.value)}>
            {["All", "Active", "Expiring Soon", "Expired", "No Active Contract", "Suspended"].map((value) => <option key={value}>{value}</option>)}
          </select>
          <select className="select" value={filters.expiry} onChange={(event) => updateFilter("expiry", event.target.value)}>
            <option value="All">Any expiry</option>
            <option value="30">Expiring within 30 days</option>
            <option value="60">Expiring within 60 days</option>
            <option value="90">Expiring within 90 days</option>
            <option value="180">Expiring within 180 days</option>
          </select>
          <select className="select" value={filters.active} onChange={(event) => updateFilter("active", event.target.value)}>
            <option value="All">Any active contract</option>
            <option value="Yes">Has active contract</option>
            <option value="No">No active contract</option>
          </select>
          <select className="select" value={filters.uncovered} onChange={(event) => updateFilter("uncovered", event.target.value)}>
            <option value="All">Any uncovered state</option>
            <option value="Yes">Has uncovered equipment</option>
            <option value="No">Fully covered</option>
          </select>
          <select className="select" value={filters.pm} onChange={(event) => updateFilter("pm", event.target.value)}>
            <option value="All">Any PM coverage</option>
            <option value="Yes">PM included</option>
            <option value="No">PM not recorded</option>
          </select>
          <select className="select" value={filters.labor} onChange={(event) => updateFilter("labor", event.target.value)}>
            <option value="All">Any labor coverage</option>
            <option value="Yes">Labor included</option>
            <option value="No">Labor not recorded</option>
          </select>
          <input className="input" type="number" min="0" max="100" value={filters.coverage} onChange={(event) => updateFilter("coverage", event.target.value)} placeholder="Min coverage %" />
          <select className="select" value={filters.owner} onChange={(event) => updateFilter("owner", event.target.value)}>
            {owners.map((owner) => <option key={owner}>{owner}</option>)}
          </select>
          <button className="button button-soft" onClick={clearFilters}>Clear filters</button>
        </div>
        <div className="muted">{visibleRows.length} hospital record(s) shown</div>
      </section>

      <section className="card hospital-status-table-card">
        {visibleRows.length ? (
          <>
            <div className="table-wrap hospital-status-desktop-table">
              <table className="table">
                <thead>
                  <tr>
                    <th>Hospital / Client</th>
                    <th>Site</th>
                    <th>Active Contract Status</th>
                    <th>Contract Number</th>
                    <th>Contract Type</th>
                    <th>Contract Start Date</th>
                    <th>Contract End Date</th>
                    <th>Days Until Expiry</th>
                    <th>Installed Equipment</th>
                    <th>Contracted Equipment</th>
                    <th>Uncovered Equipment</th>
                    <th>Contract Coverage %</th>
                    <th>PM Included</th>
                    <th>Labor Included</th>
                    <th>PM Visits Required</th>
                    <th>PM Visits Completed</th>
                    <th>Renewal Status</th>
                    <th>Account Owner</th>
                    <th>Recommended Next Action</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map((row) => (
                    <tr key={row.clientName}>
                      <td className="strong">{row.clientName}</td>
                      <td>{row.siteName}</td>
                      <td><span className={statusBadgeClass(row.contractStatus)}>{row.contractStatus}</span></td>
                      <td>{row.activeContractNumber}</td>
                      <td>{row.activeContractType}</td>
                      <td>{row.contractStartDate || "Not recorded"}</td>
                      <td>{row.contractEndDate || "Not recorded"}</td>
                      <td>{row.daysUntilExpiry ?? "Not recorded"}</td>
                      <td>{row.installedEquipmentCount}</td>
                      <td>{row.contractedEquipmentCount}</td>
                      <td>{row.uncoveredEquipmentCount}</td>
                      <td>{row.coveragePercentage}%</td>
                      <td>{row.pmIncluded ? "Yes" : "Not recorded"}</td>
                      <td>{row.laborIncluded ? "Yes" : "Not recorded"}</td>
                      <td>{row.pmVisitsRequired}</td>
                      <td>{row.pmVisitsCompleted}</td>
                      <td>{row.renewalStatus}</td>
                      <td>{row.accountOwner}</td>
                      <td>{row.recommendedNextAction}</td>
                      <td>
                        <div className="row-actions">
                          <button className="button button-soft" onClick={() => setExpandedHospital(expandedHospital === row.clientName ? "" : row.clientName)}>Details</button>
                          {row.activeContractId ? <button className="button button-soft" onClick={() => onOpenContract(row.activeContractId)}>View Contract</button> : null}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="hospital-status-mobile-list">
              {visibleRows.map((row) => (
                <article className="hospital-status-mobile-card" key={row.clientName}>
                  <div className="hospital-head">
                    <div>
                      <div className="hospital-title">{row.clientName}</div>
                      <div className="hospital-subtitle">{row.activeContractNumber}</div>
                    </div>
                    <span className={statusBadgeClass(row.contractStatus)}>{row.contractStatus}</span>
                  </div>
                  <div className="hospital-stats">
                    <div className="stat-box"><div className="stat-label">Expiry</div><div className="stat-value">{row.daysUntilExpiry ?? "N/R"}</div></div>
                    <div className="stat-box"><div className="stat-label">Coverage</div><div className="stat-value">{row.coveragePercentage}%</div></div>
                    <div className="stat-box"><div className="stat-label">Uncovered</div><div className="stat-value">{row.uncoveredEquipmentCount}</div></div>
                  </div>
                  <div className="recommendation-row"><ShieldCheck size={14} />{row.recommendedNextAction}</div>
                  <div className="actions">
                    <button className="button button-soft" onClick={() => setExpandedHospital(expandedHospital === row.clientName ? "" : row.clientName)}>Details</button>
                    {row.activeContractId ? <button className="button button-soft" onClick={() => onOpenContract(row.activeContractId)}>View Contract</button> : null}
                  </div>
                </article>
              ))}
            </div>
          </>
        ) : (
          <div className="empty-state">
            No hospitals match the selected filters.
            <div className="actions actions-friendly hospital-status-empty-actions">
              <button className="button button-soft" onClick={clearFilters}>Clear Filters</button>
              <button className="button button-primary" onClick={onBackToContracts}>Return to Contracts</button>
            </div>
          </div>
        )}
      </section>

      {expandedHospital ? (
        <section className="card hospital-status-detail">
          <div className="detail-head">
            <h2 className="section-title">{expandedHospital}</h2>
            <button className="button button-soft" onClick={() => setExpandedHospital("")}>Close details</button>
          </div>
          {visibleRows.filter((row) => row.clientName === expandedHospital).map((row) => (
            <div className="detail-grid" key={row.clientName}>
              <div><span className="strong">Active customer contract:</span> {row.activeContractNumber}</div>
              <div><span className="strong">Contracted equipment:</span> {row.contractedEquipmentCount}</div>
              <div><span className="strong">Uncovered equipment:</span> {row.uncoveredEquipment.length ? row.uncoveredEquipment.join(", ") : "None recorded"}</div>
              <div><span className="strong">PM commitments:</span> {row.pmVisitsCompleted}/{row.pmVisitsRequired}</div>
              <div><span className="strong">Labor coverage:</span> {row.laborIncluded ? "Included" : "Not recorded"}</div>
              <div><span className="strong">Renewal status:</span> {row.renewalStatus}</div>
              <div><span className="strong">Responsible owner:</span> {row.accountOwner}</div>
              <div><span className="strong">Next action:</span> {row.recommendedNextAction}</div>
            </div>
          ))}
        </section>
      ) : null}
    </div>
  );
}
