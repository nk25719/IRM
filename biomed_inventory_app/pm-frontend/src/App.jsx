import React, { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import { loadRowsFromStorage, saveRowsToStorage } from "./storage";
import DashboardCards from "./components/DashboardCards";
import EquipmentTable from "./components/EquipmentTable";
import FiltersBar from "./components/FiltersBar";
import HospitalSummary from "./components/HospitalSummary";
import ImportExportBar from "./components/ImportExportBar";
import EquipmentDetailModal from "./components/EquipmentDetailModal";
import HospitalDetailView from "./components/HospitalDetailView";
import ContractTrackerView from "./components/ContractTrackerView";
import ContractDetailView from "./components/ContractDetailView";
import {
  addMonths,
  getIntervalMonths,
  getTrackingMeta,
  getTodayIsoDate,
  getDaysUntil,
  isDueThisMonth,
} from "./utils/dateUtils";
import {
  exportRowsToJson,
  exportRowsToCsv,
  parseCsvText,
  normalizeImportedRows,
  parseImportFile,
} from "./utils/csvUtils";
import {
  createDefaultEquipmentForm,
  createEquipmentFormFromRow,
  editableStatuses,
  MAX_PM_PLACEHOLDERS,
  normalizeRows,
  normalizeStatus,
  statuses,
} from "./utils/storage";

const initialData = [
  {
    id: 1,
    hospital: "Mount Lebanon Hospital",
    contractNo: "SC/26-27/0345",
    equipment: "Patient Monitor",
    model: "B105",
    serial: "MLH-PM-001",
    pmsPerYear: 2,
    nextPmDate: "2026-05-10",
    department: "ICU",
    notes: "Coordinate with ICU nurse in charge before PM.",
    reminderDates: "2026-04-25, 2026-05-03",
    lastPmDate: "2025-11-10",
    completionDate: "",
    contractStartDate: "2026-01-01",
    contractEndDate: "2026-12-31",
    status: "Upcoming",
    engineer: "Ahmad",
    contactEmail: "biomed@mlh.example.com",
    reminder1Sent: false,
    reminder2Sent: false,
    engineerAlertSent: false,
  },
  {
    id: 2,
    hospital: "LAU Medical Center-Rizk Hospital",
    contractNo: "SC/26-26/0344",
    equipment: "Anesthesia Machine",
    model: "Aespire View",
    serial: "RIZK-AN-014",
    pmsPerYear: 4,
    nextPmDate: "2026-04-11",
    department: "OR",
    notes: "Unit used heavily on weekdays.",
    reminderDates: "2026-03-27, 2026-04-04",
    lastPmDate: "2026-01-11",
    completionDate: "",
    contractStartDate: "2026-02-01",
    contractEndDate: "2027-01-31",
    status: "Hospital notified",
    engineer: "Nadim",
    contactEmail: "maintenance@rizk.example.com",
    reminder1Sent: true,
    reminder2Sent: true,
    engineerAlertSent: true,
  },
  {
    id: 3,
    hospital: "CMC Clemenceau Medical Center",
    contractNo: "SC/25-26/0330",
    equipment: "Infusion Pump",
    model: "Volumat",
    serial: "CMC-INF-109",
    pmsPerYear: 4,
    nextPmDate: "2026-04-20",
    department: "Oncology",
    notes: "Verify battery calibration log.",
    reminderDates: "2026-04-05, 2026-04-13",
    lastPmDate: "2026-01-20",
    completionDate: "",
    contractStartDate: "2025-09-01",
    contractEndDate: "2026-08-31",
    status: "Confirmed",
    engineer: "Maya",
    contactEmail: "biomed@cmc.example.com",
    reminder1Sent: true,
    reminder2Sent: false,
    engineerAlertSent: true,
  },
  {
    id: 4,
    hospital: "Hammoud Hospital",
    contractNo: "SC/25-26/0337",
    equipment: "Defibrillator",
    model: "LIFEPAK 20",
    serial: "HAM-DEF-021",
    pmsPerYear: 2,
    nextPmDate: "2026-04-16",
    department: "ER",
    notes: "Keep backup pads ready during maintenance.",
    reminderDates: "2026-04-02, 2026-04-10",
    lastPmDate: "2025-10-16",
    completionDate: "",
    contractStartDate: "2025-07-15",
    contractEndDate: "2026-07-14",
    status: "Upcoming",
    engineer: "Karim",
    contactEmail: "biomed@hammoud.example.com",
    reminder1Sent: false,
    reminder2Sent: false,
    engineerAlertSent: false,
  },
];

function getPmCompletionCount(row) {
  return (row.pmHistory || []).filter((entry) => entry.status === "Completed").length;
}

function getPmSlotStatus(row, slotNumber) {
  const placeholder = row[`pm${slotNumber}Placeholder`];
  if (placeholder) return placeholder;
  return getPmCompletionCount(row) >= slotNumber ? "Available" : "Required";
}

function getFilledPmPlaceholderCount(row) {
  return Array.from({ length: MAX_PM_PLACEHOLDERS }, (_, index) => row[`pm${index + 1}Placeholder`])
    .filter((value) => String(value || "").trim())
    .length;
}

function getAvailablePmCount(row) {
  const requiredPmCount = Math.max(1, Number(row.pmsPerYear) || 1);
  const relevantSlots = Math.min(MAX_PM_PLACEHOLDERS, requiredPmCount);
  let availableCount = 0;
  for (let slot = 1; slot <= relevantSlots; slot += 1) {
    if (getPmSlotStatus(row, slot) === "Available") availableCount += 1;
  }
  return availableCount;
}

function appendContractHistoryEntry(baseHistory, rowSnapshot, note, actor) {
  return [
    ...(baseHistory || []),
    {
      at: new Date().toISOString(),
      by: actor || rowSnapshot.engineer || rowSnapshot.updatedBy || "System",
      note,
      contractNo: rowSnapshot.contractNo || "",
      contractStartDate: rowSnapshot.contractStartDate || "",
      contractEndDate: rowSnapshot.contractEndDate || "",
    },
  ];
}

function collectPmDatesFromImport(row) {
  const explicitPmDates = (row["PM Dates"] || row.pmDates || "")
    .split(/[;,|]/)
    .map((value) => value.trim())
    .filter(Boolean);

  const numberedPmDates = Array.from({ length: MAX_PM_PLACEHOLDERS }, (_, index) => {
    const slot = index + 1;
    return row[`PM${slot}`] || row[`PM ${slot}`] || row[`pm${slot}`] || "";
  })
    .map((value) => String(value || "").trim())
    .filter(Boolean);

  return Array.from(new Set([...explicitPmDates, ...numberedPmDates]));
}

function splitImportedEquipment(rawEquipment) {
  const text = String(rawEquipment || "").trim();
  if (!text) return [];
  return Array.from(
    new Set(
      text
        .split(/[|;\n]/)
        .map((value) => value.trim())
        .filter(Boolean)
    )
  );
}

function getEquipmentMergeKey(row) {
  return [
    row.hospital,
    row.contractNo,
    row.equipment,
    row.serial || row.model,
  ]
    .map((value) => String(value || "").trim().toLowerCase())
    .join("::");
}

function mergeImportedRows(existingRows, importedRows, today) {
  const existingByKey = new Map(existingRows.map((row) => [getEquipmentMergeKey(row), row]));
  const usedKeys = new Set();

  const mergedRows = existingRows.map((existingRow) => {
    const matchingImport = importedRows.find((importedRow) => {
      const key = getEquipmentMergeKey(importedRow);
      return key && key === getEquipmentMergeKey(existingRow) && !usedKeys.has(key);
    });

    if (!matchingImport) return existingRow;

    const key = getEquipmentMergeKey(matchingImport);
    usedKeys.add(key);

    const retainedFields = {
      id: existingRow.id,
      createdDate: existingRow.createdDate,
      pmHistory: existingRow.pmHistory || [],
      contractHistory: existingRow.contractHistory || [],
      comments: existingRow.comments || [],
      emailHistory: existingRow.emailHistory || [],
    };
    const mergedFields = Object.fromEntries(
      Object.entries(matchingImport).map(([field, value]) => [
        field,
        value === "" || value === null || value === undefined ? existingRow[field] : value,
      ])
    );

    return {
      ...existingRow,
      ...mergedFields,
      ...retainedFields,
      updatedDate: today,
      updatedBy: matchingImport.updatedBy || existingRow.updatedBy || "Import",
    };
  });

  const insertedKeys = new Set();
  const insertedRows = importedRows.filter((importedRow) => {
    const key = getEquipmentMergeKey(importedRow);
    if (!key || existingByKey.has(key) || usedKeys.has(key) || insertedKeys.has(key)) {
      return false;
    }
    insertedKeys.add(key);
    return true;
  });

  return normalizeRows([...insertedRows, ...mergedRows]);
}

function getImportValidationErrors(row) {
  const errors = [];
  if (!String(row.hospital || "").trim()) errors.push("Hospital is required");
  if (!String(row.equipment || "").trim()) errors.push("Equipment is required");
  if (!String(row.nextPmDate || "").trim()) errors.push("Next PM Date is required");
  return errors;
}

function initialPageFromPath() {
  const path = window.location.pathname.replace(/\/$/, "");
  if (path.endsWith("/hospital-status")) return "hospital-status";
  if (path.endsWith("/contracts")) return "contracts";
  return "dashboard";
}

function routeForPage(page) {
  const path = window.location.pathname.replace(/\/$/, "");
  if (path.startsWith("/aftersales/contracts") || path.startsWith("/after-sales/contracts")) {
    if (page === "contracts") return "/aftersales/contracts";
    if (page === "hospital-status") return "/aftersales/contracts/hospital-status";
    return "/aftersales/contracts/dashboard";
  }
  if (page === "contracts") return "/pm/contracts";
  if (page === "hospital-status") return "/pm/hospital-status";
  return "/pm";
}

export default function App() {
  const defaultEquipmentForm = createDefaultEquipmentForm();

  const [rows, setRows] = useState(() => normalizeRows(initialData));
  const [isStorageReady, setIsStorageReady] = useState(false);

  const [search, setSearch] = useState("");
  const [hospitalFilter, setHospitalFilter] = useState("All");
  const [statusFilter, setStatusFilter] = useState("All");
  const [timingFilter, setTimingFilter] = useState("All");
  const [sortBy, setSortBy] = useState("None");
  const [editingId, setEditingId] = useState(null);
  const [equipmentForm, setEquipmentForm] = useState(defaultEquipmentForm);
  const [detailRow, setDetailRow] = useState(null);
  const [selectedHospitalDetail, setSelectedHospitalDetail] = useState(null);
  const [selectedContractId, setSelectedContractId] = useState(null);
  const [showContractAddEquipment, setShowContractAddEquipment] = useState(false);
  const [currentPage, setCurrentPage] = useState(initialPageFromPath);
  const [hospitalSummaryFilter, setHospitalSummaryFilter] = useState("All");
  const [bulkEquipmentText, setBulkEquipmentText] = useState("");
  const [reminderWindow, setReminderWindow] = useState("next-week");
  const [reminderScheduleAt, setReminderScheduleAt] = useState("");
  const [quickActionFeedback, setQuickActionFeedback] = useState("");
  const [contractEquipmentDraft, setContractEquipmentDraft] = useState({
    equipment: "",
    serial: "",
    model: "",
    department: "",
    pmsPerYear: 1,
    nextPmDate: "",
  });
  const fileInputRef = useRef(null);
  const contractFileInputRef = useRef(null);

  const aiInsights = useMemo(() => {
    const overdueRows = rows.filter((row) => getTrackingMeta(row).isOverdue);
    const soonRows = rows.filter((row) => getTrackingMeta(row).dueSoon7);
    const grouped = overdueRows.reduce((acc, row) => {
      acc[row.hospital] = (acc[row.hospital] || 0) + 1;
      return acc;
    }, {});
    const riskiestHospital =
      Object.entries(grouped).sort((a, b) => b[1] - a[1])[0] || null;

    return {
      overdueRows,
      soonRows,
      riskiestHospital,
    };
  }, [rows]);

  useEffect(() => {
    let isMounted = true;

    async function restoreRows() {
      try {
        const storedRows = await loadRowsFromStorage();
        if (isMounted && Array.isArray(storedRows)) {
          setRows(normalizeRows(storedRows));
        }
      } catch (error) {
        console.error("Failed to load data from IndexedDB", error);
      } finally {
        if (isMounted) setIsStorageReady(true);
      }
    }

    restoreRows();

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!isStorageReady) return;
    saveRowsToStorage(rows).catch((error) => {
      console.error("Failed to save data to IndexedDB", error);
    });
  }, [rows, isStorageReady]);

  const hospitals = useMemo(() => {
    const unique = Array.from(new Set(rows.map((r) => r.hospital).filter(Boolean)));
    return ["All", ...unique];
  }, [rows]);

  const filteredRows = useMemo(() => {
    const filtered = rows.filter((row) => {
      const matchesSearch = [
        row.hospital,
        row.contractNo,
        row.equipment,
        row.model,
        row.serial,
        row.department,
        row.notes,
        row.reminderDates,
        row.lastPmDate,
        row.completionDate,
        row.engineer,
        row.updatedBy,
      ]
        .join(" ")
        .toLowerCase()
        .includes(search.toLowerCase());

      const matchesHospital = hospitalFilter === "All" || row.hospital === hospitalFilter;
      const meta = getTrackingMeta(row);
      const matchesStatus =
        statusFilter === "All" || row.status === statusFilter || (statusFilter === "Overdue" && meta.isOverdue);

      const matchesTiming =
        timingFilter === "All" ||
        (timingFilter === "Overdue only" && meta.isOverdue) ||
        (timingFilter === "Due this week" && meta.dueSoon7) ||
        (timingFilter === "Due this month" && isDueThisMonth(row.nextPmDate) && meta.effectiveStatus !== "Completed") ||
        (timingFilter === "Completed" && row.status === "Completed");

      return matchesSearch && matchesHospital && matchesStatus && matchesTiming;
    });

    return filtered.sort((a, b) => {
      if (sortBy === "Hospital") return a.hospital.localeCompare(b.hospital);
      if (sortBy === "Next PM date") return new Date(a.nextPmDate) - new Date(b.nextPmDate);

      if (sortBy === "Overdue") {
        const aOverdue = getTrackingMeta(a).isOverdue ? 0 : 1;
        const bOverdue = getTrackingMeta(b).isOverdue ? 0 : 1;
        if (aOverdue !== bOverdue) return aOverdue - bOverdue;
        return getDaysUntil(a.nextPmDate) - getDaysUntil(b.nextPmDate);
      }

      if (sortBy === "Engineer") return (a.engineer || "").localeCompare(b.engineer || "");
      return 0;
    });
  }, [rows, search, hospitalFilter, statusFilter, timingFilter, sortBy]);

  const metrics = useMemo(() => {
    const total = rows.length;
    const overdue = rows.filter((r) => getTrackingMeta(r).isOverdue).length;
    const dueThisWeek = rows.filter((r) => getTrackingMeta(r).dueSoon7).length;
    const completed = rows.filter((r) => r.status === "Completed").length;
    return { total, overdue, dueThisWeek, completed };
  }, [rows]);

  const byHospital = useMemo(() => {
    const map = {};
    rows.forEach((row) => {
      if (!map[row.hospital]) {
        map[row.hospital] = {
          total: 0,
          overdue: 0,
          upcoming: 0,
          dueSoon: 0,
          pmRequiredTotal: 0,
          pmCompletedTotal: 0,
          pmPlaceholdersFilled: 0,
          pmAvailableToDo: 0,
        };
      }
      const meta = getTrackingMeta(row);
      map[row.hospital].total += 1;
      if (meta.isOverdue) map[row.hospital].overdue += 1;
      if (row.status === "Upcoming") map[row.hospital].upcoming += 1;
      if (meta.dueSoon7) map[row.hospital].dueSoon += 1;
      map[row.hospital].pmRequiredTotal += Number(row.pmsPerYear) || 1;
      map[row.hospital].pmCompletedTotal += getPmCompletionCount(row);
      map[row.hospital].pmPlaceholdersFilled += getFilledPmPlaceholderCount(row);
      map[row.hospital].pmAvailableToDo += getAvailablePmCount(row);
    });
    return Object.entries(map).map(([hospital, values]) => ({ hospital, ...values }));
  }, [rows]);

  const hospitalDetailRows = useMemo(
    () => rows.filter((row) => row.hospital === selectedHospitalDetail),
    [rows, selectedHospitalDetail]
  );

  const contractRows = useMemo(() => {
    const contractMap = new Map();
    rows.forEach((row) => {
      const key = `${row.hospital || ""}::${row.contractNo || ""}`;
      if (!contractMap.has(key)) {
        const endDate = row.contractEndDate || "";
        const daysLeft = endDate ? getDaysUntil(endDate) : Number.POSITIVE_INFINITY;
        contractMap.set(key, {
          id: key,
          hospital: row.hospital,
          contractNo: row.contractNo,
          contractStartDate: row.contractStartDate,
          contractEndDate: endDate,
          daysLeft,
          equipment: [],
          pmRequiredTotal: 0,
          pmDates: [],
          contractHistory: [],
        });
      }
      const contractRecord = contractMap.get(key);
      const equipmentLabel = [row.equipment || "Unnamed equipment", row.serial ? `(${row.serial})` : ""].join(" ").trim();
      const pmDates = collectPmDatesFromImport(row);
      contractRecord.equipment.push(equipmentLabel);
      contractRecord.pmRequiredTotal += Math.max(1, Number(row.pmsPerYear) || 1);
      contractRecord.pmDates.push(...(pmDates.length ? pmDates : [row.nextPmDate].filter(Boolean)));
      contractRecord.contractHistory.push(...(row.contractHistory || []));
    });

    return Array.from(contractMap.values())
      .filter((item) => item.hospital || item.contractNo)
      .map((item) => ({
        ...item,
        equipment: Array.from(new Set(item.equipment)).sort(),
        pmDates: Array.from(new Set(item.pmDates)).sort(),
        contractHistory: item.contractHistory
          .filter((entry) => entry.note || entry.contractNo || entry.contractEndDate || entry.contractStartDate)
          .sort((a, b) => new Date(b.at || 0) - new Date(a.at || 0)),
      }))
      .sort((a, b) => a.daysLeft - b.daysLeft);
  }, [rows]);

  const parsedBulkItems = useMemo(
    () => parseBulkEquipmentLines(bulkEquipmentText),
    [bulkEquipmentText]
  );

  const editingPmSummary = useMemo(() => {
    if (!editingId) return null;
    const row = rows.find((item) => item.id === editingId);
    if (!row) return null;
    const completedPmCount = getPmCompletionCount(row);
    const requiredPmCount = Number(row.pmsPerYear) || 1;
    return {
      completedPmCount,
      requiredPmCount,
      pm1: completedPmCount >= 1 ? "Available" : "Required",
      pm2: completedPmCount >= 2 ? "Available" : "Required",
      pm3: completedPmCount >= 3 ? "Available" : "Required",
      otherPm:
        requiredPmCount > 3
          ? `${Math.max(0, completedPmCount - 3)}/${requiredPmCount - 3} available`
          : "N/A",
    };
  }, [editingId, rows]);

  function openHospitalDetail(hospital) {
    setSelectedHospitalDetail(hospital);
    setCurrentPage("hospital-detail");
  }

  function navigatePage(page) {
    setCurrentPage(page);
    window.history.pushState(null, "", routeForPage(page));
  }

  function openContractsView() {
    navigatePage("contracts");
  }

  function openContractDetail(contractId) {
    setSelectedContractId(contractId);
    setContractEquipmentDraft({
      equipment: "",
      serial: "",
      model: "",
      department: "",
      pmsPerYear: 1,
      nextPmDate: "",
    });
    setCurrentPage("contract-detail");
  }

  function handleContractEquipmentDraftChange(field, value) {
    setContractEquipmentDraft((current) => ({ ...current, [field]: value }));
  }

  function handleAddEquipmentToContract(contractId, draft) {
    const targetContract = contractRows.find((contract) => contract.id === contractId);
    if (!targetContract || !String(draft.equipment || "").trim()) return;

    const today = getTodayIsoDate();
    const actor = "Contract Editor";
    setRows((current) => [
      {
        id: Date.now(),
        hospital: targetContract.hospital,
        contractNo: targetContract.contractNo,
        contractStartDate: targetContract.contractStartDate,
        contractEndDate: targetContract.contractEndDate,
        equipment: draft.equipment.trim(),
        serial: String(draft.serial || "").trim(),
        model: String(draft.model || "").trim(),
        department: String(draft.department || "").trim(),
        pmsPerYear: Math.max(1, Number(draft.pmsPerYear) || 1),
        nextPmDate: draft.nextPmDate || "",
        status: "Upcoming",
        reminderDates: "",
        reminder1Sent: false,
        reminder2Sent: false,
        engineerAlertSent: false,
        notes: "Added from contract details view.",
        pmHistory: [],
        contractHistory: appendContractHistoryEntry([], targetContract, "Equipment added from contract detail view", actor),
        createdDate: today,
        updatedDate: today,
        updatedBy: actor,
        engineer: "",
        contactEmail: "",
      },
      ...current,
    ]);

    setContractEquipmentDraft({
      equipment: "",
      serial: "",
      model: "",
      department: "",
      pmsPerYear: 1,
      nextPmDate: "",
    });
  }

  function handleRemoveEquipmentFromContract(rowId) {
    setRows((current) => current.filter((row) => row.id !== rowId));
  }

  async function handleImportFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const rawRows = await parseImportFile(file);
      const normalized = normalizeImportedRows(rawRows, normalizeStatus, getTodayIsoDate);
      const validRows = [];
      const invalidRows = [];

      normalized.forEach((row, index) => {
        const errors = getImportValidationErrors(row);
        if (errors.length) invalidRows.push({ index: index + 2, errors });
        else validRows.push(row);
      });

      if (validRows.length) {
        const today = getTodayIsoDate();
        setRows((current) => mergeImportedRows(current, validRows, today));
        setQuickActionFeedback(
          `Imported ${validRows.length} valid record(s) with add/merge behavior${
            invalidRows.length ? `; skipped ${invalidRows.length} row(s) missing required fields.` : "."
          }`
        );
      }
      else if (invalidRows.length) {
        setQuickActionFeedback("No rows imported. Required fields: Hospital, Equipment, Next PM Date.");
      } else setQuickActionFeedback("No valid records found in imported file.");
    } catch (error) {
      console.error("Import failed", error);
      setQuickActionFeedback(error.message || "Import failed. Please check file format.");
    }

    event.target.value = "";
  }

  async function handleImportContractsFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;

    let importedRows = [];
    try {
      importedRows = await parseImportFile(file);
    } catch (error) {
      console.error("Contract import failed", error);
      setQuickActionFeedback(error.message || "Contract import failed.");
      event.target.value = "";
      return;
    }

    if (!importedRows.length) {
      event.target.value = "";
      return;
    }

    const normalizedContracts = importedRows
      .flatMap((row) => {
        const equipmentField = row.Equipment || row.equipment || row.Subsystem || row.subsystem || "";
        const equipmentItems = splitImportedEquipment(equipmentField);
        const baseContract = {
          hospital: row.Hospital || row.hospital || "",
          contractNo: row["Contract No."] || row.contractNo || row["Contract Number"] || "",
          model: row.Model || row.model || "",
          serial: row["Serial Number"] || row.serial || row.Serial || "",
          contractStartDate: row["Contract Start Date"] || row.contractStartDate || "",
          contractEndDate: row["Contract End Date"] || row.contractEndDate || "",
          pmsPerYear: Math.max(1, Number(row["PMs per Year"] || row.pmsPerYear || 1) || 1),
          nextPmDate: row["Next PM Date"] || row.nextPmDate || "",
          pmDates: collectPmDatesFromImport(row),
        };

        if (!equipmentItems.length) {
          return [{ ...baseContract, equipment: "" }];
        }

        return equipmentItems.map((equipmentItem) => ({
          ...baseContract,
          equipment: equipmentItem,
        }));
      })
      .filter((row) => row.hospital || row.contractNo);

    if (!normalizedContracts.length) {
      event.target.value = "";
      return;
    }

    setRows((current) =>
      normalizedContracts.reduce((acc, importedContract, index) => {
        const matches = acc.filter(
          (row) =>
            row.hospital === importedContract.hospital &&
            row.contractNo === importedContract.contractNo &&
            (!importedContract.equipment || row.equipment === importedContract.equipment)
        );

        if (!matches.length) {
          const today = getTodayIsoDate();
          const actor = "Contracts Import";
          const pmPlaceholders = Object.fromEntries(
            Array.from({ length: MAX_PM_PLACEHOLDERS }, (_, slotIndex) => {
              const slot = slotIndex + 1;
              return [`pm${slot}Placeholder`, importedContract.pmDates[slotIndex] || ""];
            })
          );
          return [
            ...acc,
            normalizeRows([
              {
                id: Date.now() + index,
                hospital: importedContract.hospital,
                contractNo: importedContract.contractNo,
                equipment: importedContract.equipment || "Imported contract item",
                model: importedContract.model,
                serial: importedContract.serial,
                department: "",
                pmsPerYear: importedContract.pmsPerYear,
                nextPmDate: importedContract.nextPmDate || importedContract.pmDates[0] || "",
                lastPmDate: "",
                completionDate: "",
                reminderDates: "",
                status: "Upcoming",
                contractStartDate: importedContract.contractStartDate,
                contractEndDate: importedContract.contractEndDate,
                engineer: "",
                contactEmail: "",
                notes: "Created from contract import.",
                updatedBy: actor,
                createdDate: today,
                updatedDate: today,
                reminder1Sent: false,
                reminder2Sent: false,
                engineerAlertSent: false,
                contractHistory: appendContractHistoryEntry(
                  [],
                  importedContract,
                  "Contract imported with PM schedule",
                  actor
                ),
                ...pmPlaceholders,
              },
            ])[0],
          ];
        }

        return acc.map((row) => {
          const isMatch =
            row.hospital === importedContract.hospital &&
            row.contractNo === importedContract.contractNo &&
            (!importedContract.equipment || row.equipment === importedContract.equipment);
          if (!isMatch) return row;

          const hasContractChange =
            importedContract.contractStartDate !== row.contractStartDate ||
            importedContract.contractEndDate !== row.contractEndDate;
          const actor = row.updatedBy || row.engineer || "System";
          const pmPlaceholders = Object.fromEntries(
            Array.from({ length: MAX_PM_PLACEHOLDERS }, (_, slotIndex) => {
              const slot = slotIndex + 1;
              const nextValue = importedContract.pmDates[slotIndex];
              const key = `pm${slot}Placeholder`;
              return [key, nextValue || row[key] || ""];
            })
          );

          return {
            ...row,
            contractStartDate: importedContract.contractStartDate || row.contractStartDate,
            contractEndDate: importedContract.contractEndDate || row.contractEndDate,
            pmsPerYear: importedContract.pmsPerYear || row.pmsPerYear,
            nextPmDate: importedContract.nextPmDate || importedContract.pmDates[0] || row.nextPmDate,
            ...pmPlaceholders,
            contractHistory: hasContractChange
              ? appendContractHistoryEntry(
                  row.contractHistory,
                  { ...row, ...importedContract },
                  "Contract dates updated from imported contracts file",
                  actor
                )
              : row.contractHistory || [],
          };
        });
      }, current)
    );

    event.target.value = "";
  }

  function exportContractsToCsv() {
    const headers = [
      "Hospital",
      "Contract No.",
      "Contract Start Date",
      "Contract End Date",
      "Equipment in Contract",
      "PMs Required (Yearly)",
      "PM Dates",
      "Days Left",
    ];
    const csv = [headers.join(",")]
      .concat(
        contractRows.map((contract) =>
          [
            contract.hospital,
            contract.contractNo,
            contract.contractStartDate,
            contract.contractEndDate,
            contract.equipment.join(" | "),
            contract.pmRequiredTotal,
            contract.pmDates.join(" | "),
            contract.daysLeft,
          ]
            .map((value) => `"${String(value ?? "").replace(/"/g, '""')}"`)
            .join(",")
        )
      )
      .join("\n");

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "pm-contracts-export.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function updateRow(id, patch, actor = "System") {
    const today = getTodayIsoDate();
    setRows((current) =>
      current.map((row) =>
        row.id === id
          ? {
              ...row,
              ...patch,
              updatedDate: today,
              updatedBy: actor || row.updatedBy || row.engineer || "System",
            }
          : row
      )
    );
  }

  function handleFormChange(field, value) {
    setEquipmentForm((current) => ({ ...current, [field]: value }));
  }

  function resetForm() {
    setEquipmentForm(createDefaultEquipmentForm());
    setBulkEquipmentText("");
    setEditingId(null);
    setShowContractAddEquipment(false);
  }

  function startAdd() {
    setEquipmentForm(createDefaultEquipmentForm());
    setBulkEquipmentText("");
    setEditingId(null);
    setCurrentPage("contracts");
    setShowContractAddEquipment(true);
  }

  function startEdit(row) {
    setEquipmentForm(createEquipmentFormFromRow(row));
    setBulkEquipmentText("");
    setEditingId(row.id);
    setCurrentPage("contracts");
    setShowContractAddEquipment(true);
  }

  function toggleContractAddEquipment() {
    setShowContractAddEquipment((current) => !current);
    setCurrentPage("contracts");
  }

  function handleDelete(id) {
    setRows((current) => current.filter((row) => row.id !== id));
  }

  function parseBulkEquipmentLines(text) {
    if (!text.trim()) return [];
    if (!text.includes("|")) {
      return parseCsvText(`Equipment,Serial,Model,Department\n${text}`)
        .map((row) => ({
          equipment: String(row.Equipment || "").trim(),
          serial: String(row.Serial || "").trim(),
          model: String(row.Model || "").trim(),
          department: String(row.Department || "").trim(),
        }))
        .filter((item) => item.equipment);
    }

    const delimiter = "|";
    return text
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [equipment, serial, model, department] = line.split(delimiter).map((part) => (part || "").trim());
        return { equipment, model, serial, department };
      })
      .filter((item) => item.equipment);
  }

  function markComplete(row) {
    const today = getTodayIsoDate();
    const intervalMonths = Math.max(1, Math.round(12 / (Number(row.pmsPerYear) || 1)));
    const actor = row.engineer || row.updatedBy || "System";

    updateRow(
      row.id,
      {
        status: "Completed",
        completionDate: today,
        lastPmDate: today,
        nextPmDate: addMonths(today, intervalMonths),
        pmHistory: [
          ...(row.pmHistory || []),
          {
            date: today,
            status: "Completed",
            updatedBy: actor,
            notes: "Marked complete from equipment table",
          },
        ],
      },
      actor
    );
  }

  function handleSubmitEquipment(event) {
    event.preventDefault();
    if (!String(equipmentForm.hospital || "").trim()) {
      setQuickActionFeedback("Hospital is required before saving equipment.");
      return;
    }
    if (!editingId && !bulkEquipmentText.trim() && !String(equipmentForm.equipment || "").trim()) {
      setQuickActionFeedback("Equipment is required before saving.");
      return;
    }
    if (!String(equipmentForm.nextPmDate || "").trim()) {
      setQuickActionFeedback("Next PM Date is required before saving equipment.");
      return;
    }

    const today = getTodayIsoDate();
    const normalizedPmsPerYear = Number(equipmentForm.pmsPerYear) || 1;
    const intervalMonths = Math.max(1, Math.round(12 / normalizedPmsPerYear));
    const actor = equipmentForm.updatedBy || equipmentForm.engineer || "System";
    const autoNextPmDate =
      equipmentForm.status === "Completed" && equipmentForm.completionDate
        ? addMonths(equipmentForm.completionDate, intervalMonths)
        : equipmentForm.nextPmDate;

    const payload = {
      ...equipmentForm,
      pmsPerYear: normalizedPmsPerYear,
      nextPmDate: autoNextPmDate,
      updatedBy: actor,
      lastPmDate:
        equipmentForm.status === "Completed" && equipmentForm.completionDate
          ? equipmentForm.completionDate
          : equipmentForm.lastPmDate,
    };

    const bulkItems = !editingId ? parsedBulkItems : [];
    const isBulkAdd = bulkItems.length > 0;

    if (editingId) {
      const existingRow = rows.find((row) => row.id === editingId);
      const completionChanged =
        payload.status === "Completed" &&
        payload.completionDate &&
        payload.completionDate !== existingRow?.completionDate;
      const contractChanged =
        payload.contractNo !== existingRow?.contractNo ||
        payload.contractStartDate !== existingRow?.contractStartDate ||
        payload.contractEndDate !== existingRow?.contractEndDate;

      updateRow(
        editingId,
        {
          ...payload,
          contractHistory: contractChanged
            ? appendContractHistoryEntry(
                existingRow?.contractHistory,
                payload,
                "Contract details updated from equipment form",
                actor
              )
            : existingRow?.contractHistory || [],
          pmHistory: completionChanged
            ? [
                ...(existingRow?.pmHistory || []),
                {
                  date: payload.completionDate,
                  status: "Completed",
                  updatedBy: actor,
                  notes: "Completed from edit form",
                },
              ]
            : existingRow?.pmHistory || [],
        },
        actor
      );
    } else {
      setRows((current) => [
        ...(isBulkAdd
          ? bulkItems.map((item, index) => ({
              id: Date.now() + index,
              reminder1Sent: false,
              reminder2Sent: false,
              engineerAlertSent: false,
              createdDate: today,
              updatedDate: today,
              updatedBy: actor,
              contractHistory:
                payload.contractNo || payload.contractStartDate || payload.contractEndDate
                  ? appendContractHistoryEntry([], payload, "Contract details added with equipment", actor)
                  : [],
              pmHistory:
                payload.status === "Completed" && payload.completionDate
                  ? [
                      {
                        date: payload.completionDate,
                        status: "Completed",
                        updatedBy: actor,
                        notes: "Initial completed entry",
                      },
                    ]
                  : [],
              ...payload,
              equipment: item.equipment,
              model: item.model || payload.model,
              serial: item.serial || payload.serial,
              department: item.department || payload.department,
            }))
          : [
              {
                id: Date.now(),
                reminder1Sent: false,
                reminder2Sent: false,
                engineerAlertSent: false,
                createdDate: today,
                updatedDate: today,
                updatedBy: actor,
                contractHistory:
                  payload.contractNo || payload.contractStartDate || payload.contractEndDate
                    ? appendContractHistoryEntry([], payload, "Contract details added with equipment", actor)
                    : [],
                pmHistory:
                  payload.status === "Completed" && payload.completionDate
                    ? [
                        {
                          date: payload.completionDate,
                          status: "Completed",
                          updatedBy: actor,
                          notes: "Initial completed entry",
                        },
                      ]
                    : [],
                ...payload,
              },
            ]),
        ...current,
      ]);
    }

    setBulkEquipmentText("");
    resetForm();
  }

  function badgeClass(status, meta) {
    if (status === "Completed") return "badge badge-completed";
    if (status === "Deferred") return "badge badge-deferred";
    if (meta.isOverdue) return "badge badge-overdue";
    if (meta.dueSoon7) return "badge badge-due-soon";
    if (status === "Confirmed") return "badge badge-confirmed";
    return "badge badge-default";
  }

  function handleUpcomingReminderAction() {
    if (!reminderScheduleAt) {
      setQuickActionFeedback("Please choose a definite reminder date and time first.");
      return;
    }

    const windowDays = reminderWindow === "next-month" ? 30 : 7;
    const eligibleRows = rows.filter((row) => {
      const meta = getTrackingMeta(row);
      return meta.daysUntil >= 0 && meta.daysUntil <= windowDays && meta.effectiveStatus !== "Completed";
    });

    if (!eligibleRows.length) {
      setQuickActionFeedback("No upcoming PM items match your selected window.");
      return;
    }

    const ids = new Set(eligibleRows.map((row) => row.id));
    setRows((current) =>
      current.map((row) =>
        ids.has(row.id)
          ? {
              ...row,
              reminder1Sent: true,
              status: row.status === "Upcoming" ? "Hospital notified" : row.status,
            }
          : row
      )
    );

    setQuickActionFeedback(
      `Scheduled ${eligibleRows.length} reminder(s) for ${new Date(reminderScheduleAt).toLocaleString()} (${reminderWindow === "next-month" ? "next month" : "next week"}).`
    );
  }

  function handleNotifyEngineersQuickAction(targetRows = rows, reason = "Engineer notification") {
    const actionableRows = targetRows.filter((row) => getTrackingMeta(row).effectiveStatus !== "Completed");
    if (!actionableRows.length) {
      setQuickActionFeedback("No pending PM items found to notify engineers.");
      return;
    }

    const ids = new Set(actionableRows.map((row) => row.id));
    setRows((current) =>
      current.map((row) =>
        ids.has(row.id)
          ? {
              ...row,
              engineerAlertSent: true,
              updatedBy: row.engineer || row.updatedBy || "System",
            }
          : row
      )
    );
    logHospitalEmailHistory(actionableRows, reason);
    setQuickActionFeedback(`Engineers notified for ${actionableRows.length} equipment item(s).`);
  }

  function handleHospitalEmailQuickAction(targetRows = [], subject = "PM follow-up email", options = {}) {
    const { includeCompleted = false } = options;
    const actionableRows = targetRows.filter((row) =>
      includeCompleted ? getTrackingMeta(row).effectiveStatus === "Completed" : getTrackingMeta(row).effectiveStatus !== "Completed"
    );
    if (!actionableRows.length) {
      setQuickActionFeedback(includeCompleted ? "No completed PM items found for email follow-up." : "No pending PM items found for email follow-up.");
      return;
    }

    const targetIds = new Set(actionableRows.map((row) => row.id));
    const stageCounts = { r1: 0, r2: 0, alert: 0, completed: 0, noChange: 0 };

    setRows((current) =>
      current.map((row) => {
        if (!targetIds.has(row.id)) return row;

        const patch = {
          updatedBy: row.updatedBy || "PM Coordinator",
          updatedDate: getTodayIsoDate(),
        };

        if (includeCompleted) {
          stageCounts.completed += 1;
        } else if (!row.reminder1Sent) {
          patch.reminder1Sent = true;
          if (row.status === "Upcoming") patch.status = "Hospital notified";
          stageCounts.r1 += 1;
        } else if (!row.reminder2Sent) {
          patch.reminder2Sent = true;
          stageCounts.r2 += 1;
        } else if (!row.engineerAlertSent) {
          patch.engineerAlertSent = true;
          stageCounts.alert += 1;
        } else {
          stageCounts.noChange += 1;
        }

        return { ...row, ...patch };
      })
    );

    logHospitalEmailHistory(actionableRows, subject);

    const feedbackParts = [];
    if (stageCounts.r1) feedbackParts.push(`R1 sent for ${stageCounts.r1}`);
    if (stageCounts.r2) feedbackParts.push(`R2 sent for ${stageCounts.r2}`);
    if (stageCounts.alert) feedbackParts.push(`Engineer alert sent for ${stageCounts.alert}`);
    if (stageCounts.completed) feedbackParts.push(`Completed PM email sent for ${stageCounts.completed}`);
    if (stageCounts.noChange) feedbackParts.push(`${stageCounts.noChange} already fully updated`);
    setQuickActionFeedback(`Email follow-up updated ${actionableRows.length} item(s): ${feedbackParts.join(" · ")}.`);
  }



  function addCommunicationEntry(rowIds, entryBuilder) {
    const idSet = new Set(rowIds);
    setRows((current) =>
      current.map((row) => {
        if (!idSet.has(row.id)) return row;
        return entryBuilder(row);
      })
    );
  }

  function handleAddHospitalComment({ rowIds, note, by }) {
    const at = new Date().toISOString();
    addCommunicationEntry(rowIds, (row) => ({
      ...row,
      comments: [...(row.comments || []), { at, by, note }],
      updatedBy: by || row.updatedBy,
      updatedDate: getTodayIsoDate(),
    }));
    setQuickActionFeedback(`Comment added to ${rowIds.length} selected item(s).`);
  }

  function logHospitalEmailHistory(targetRows, subject = "PM follow-up email") {
    const at = new Date().toISOString();
    const rowIds = targetRows.map((row) => row.id);
    addCommunicationEntry(rowIds, (row) => ({
      ...row,
      emailHistory: [
        ...(row.emailHistory || []),
        {
          at,
          by: row.engineer || row.updatedBy || "PM Coordinator",
          subject,
          note: `Email draft opened for ${row.contactEmail || "hospital contact"}`,
        },
      ],
    }));
  }

  function renderHospitalSummaryPanel() {
    return (
      <HospitalSummary
        byHospital={byHospital}
        selectedHospital={selectedHospitalDetail}
        onSelectHospital={openHospitalDetail}
        hospitalSummaryFilter={hospitalSummaryFilter}
        onHospitalSummaryFilterChange={setHospitalSummaryFilter}
        quickActions={
          <div className="status-workflow-panel">
            <div>
              <div className="strong">Automation recommendations</div>
              <div className="muted">
                {aiInsights.riskiestHospital
                  ? `${aiInsights.riskiestHospital[0]} has the highest overdue load (${aiInsights.riskiestHospital[1]} item(s)).`
                  : "No overdue hospital risk detected."}
              </div>
              <div className="muted">
                {aiInsights.soonRows.length} item(s) are due within 7 days and ready for availability confirmation.
              </div>
            </div>
            <div className="actions">
              <button className="button button-soft" onClick={markOverdueReminderOneSent}>Mark overdue R1</button>
              <button className="button button-soft" onClick={markOverdueReminderTwoSent}>Mark overdue R2</button>
              <button className="button button-primary" onClick={markOverdueEngineerAlertSent}>Alert engineers</button>
            </div>
          </div>
        }
      />
    );
  }

  function showOverdueQuickAction() {
    setTimingFilter("Overdue only");
    navigatePage("dashboard");
    setQuickActionFeedback("Showing overdue equipment in the main table.");
  }

  function applyStatusQuickAction({ label, matcher, patch }) {
    const targetRows = rows.filter(matcher);
    if (!targetRows.length) {
      setQuickActionFeedback(`No equipment matched for "${label}".`);
      return;
    }

    const targetIds = new Set(targetRows.map((row) => row.id));
    setRows((prevRows) =>
      prevRows.map((row) => (targetIds.has(row.id) ? { ...row, ...patch } : row))
    );
    setQuickActionFeedback(`${label} applied to ${targetRows.length} equipment item(s).`);
  }

  function markOverdueReminderOneSent() {
    applyStatusQuickAction({
      label: "Reminder 1 marked as sent for overdue equipment",
      matcher: (row) => getTrackingMeta(row).isOverdue && !row.reminder1Sent,
      patch: { reminder1Sent: true },
    });
  }

  function markOverdueReminderTwoSent() {
    applyStatusQuickAction({
      label: "Reminder 2 marked as sent for overdue equipment",
      matcher: (row) => getTrackingMeta(row).isOverdue && !row.reminder2Sent,
      patch: { reminder2Sent: true },
    });
  }

  function markOverdueEngineerAlertSent() {
    applyStatusQuickAction({
      label: "Engineer alert marked as sent for overdue equipment",
      matcher: (row) => getTrackingMeta(row).isOverdue && !row.engineerAlertSent,
      patch: { engineerAlertSent: true },
    });
  }

  function handleMetricFilterSelect(nextTimingFilter) {
    setTimingFilter(nextTimingFilter);
    navigatePage("dashboard");
    if (nextTimingFilter === "All") {
      setQuickActionFeedback("Showing all equipment in the main table.");
      return;
    }
    if (nextTimingFilter === "Due this week") {
      setQuickActionFeedback("Showing equipment due this week in the main table.");
      return;
    }
    if (nextTimingFilter === "Overdue only") {
      setQuickActionFeedback("Showing overdue equipment in the main table.");
      return;
    }
    if (nextTimingFilter === "Completed") {
      setQuickActionFeedback("Showing completed maintenance items in the main table.");
    }
  }

  return (
    <div className="app-shell">
      <div className="app-container">
        <div className="topbar">
          <div>
            <h1 className="page-title">Preventive Maintenance Tracker</h1>
            <p className="subtitle">User-friendly PM dashboard with CSV/Excel import, COM history, and reminder tracking.</p>
          </div>

          <div className="erp-top-actions">
            <a className="button button-soft" href="/portal">ERP Portal</a>
            <a className="button button-soft" href="/warehouse">Warehouse</a>
            {currentPage === "dashboard" ? (
      <ImportExportBar
                fileInputRef={fileInputRef}
                onImportChange={handleImportFile}
                onExportCsv={() => exportRowsToCsv(rows, getIntervalMonths)}
                onExportJson={() => exportRowsToJson(rows)}
              />
            ) : null}
          </div>
        </div>

        {currentPage === "dashboard" ? (
          <DashboardCards metrics={metrics} timingFilter={timingFilter} onMetricFilterSelect={handleMetricFilterSelect} />
        ) : null}
        <div className="view-toggle-row">
          <button className={`button ${currentPage === "dashboard" ? "button-primary" : ""}`} onClick={() => navigatePage("dashboard")}>
            Dashboard
          </button>
          <button className={`button ${currentPage === "hospital-status" ? "button-primary" : ""}`} onClick={() => navigatePage("hospital-status")}>
            Hospital Equipment Status
          </button>
          <button className={`button ${currentPage === "contracts" ? "button-primary" : ""}`} onClick={openContractsView}>
            Contracts View
          </button>
        </div>

        {currentPage === "dashboard" ? (
          <FiltersBar
            search={search}
            setSearch={setSearch}
            hospitalFilter={hospitalFilter}
            setHospitalFilter={setHospitalFilter}
            statusFilter={statusFilter}
            setStatusFilter={setStatusFilter}
            timingFilter={timingFilter}
            setTimingFilter={setTimingFilter}
            sortBy={sortBy}
            setSortBy={setSortBy}
            hospitals={hospitals}
            statuses={statuses}
          />
        ) : null}

        {currentPage === "hospital-detail" ? (
          <HospitalDetailView
            hospital={selectedHospitalDetail}
            rows={hospitalDetailRows}
            getTrackingMeta={getTrackingMeta}
            onSendHospitalEmail={handleHospitalEmailQuickAction}
            onAddHospitalComment={handleAddHospitalComment}
            quickActionFeedback={quickActionFeedback}
          />
        ) : currentPage === "hospital-status" ? (
          renderHospitalSummaryPanel()
        ) : currentPage === "contracts" ? (
          <ContractTrackerView
            contracts={contractRows}
            onOpenContract={openContractDetail}
            contractFileInputRef={contractFileInputRef}
            onImportContracts={handleImportContractsFile}
            onExportContractsCsv={exportContractsToCsv}
            isAddEquipmentVisible={showContractAddEquipment}
            onToggleAddEquipment={toggleContractAddEquipment}
            addEquipmentPanel={
          <div className="card form-card">
            <div className="form-head">
              <h2 className="section-title">{editingId ? "Edit Equipment" : "Add Equipment"}</h2>
              <button className="button" onClick={resetForm}>
                Cancel
              </button>
            </div>
            <form className="equipment-form" onSubmit={handleSubmitEquipment}>
              <div className="form-grid">
                <input required className="input" placeholder="Hospital" value={equipmentForm.hospital} onChange={(e) => handleFormChange("hospital", e.target.value)} />
                <input className="input" placeholder="Contract No." value={equipmentForm.contractNo} onChange={(e) => handleFormChange("contractNo", e.target.value)} />
                <input required={!bulkEquipmentText.trim()} className="input" placeholder="Equipment" value={equipmentForm.equipment} onChange={(e) => handleFormChange("equipment", e.target.value)} />
                <input className="input" placeholder="Model" value={equipmentForm.model} onChange={(e) => handleFormChange("model", e.target.value)} />
                <input className="input" placeholder="Serial" value={equipmentForm.serial} onChange={(e) => handleFormChange("serial", e.target.value)} />
                <input className="input" placeholder="Department" value={equipmentForm.department} onChange={(e) => handleFormChange("department", e.target.value)} />
                <input className="input" type="number" min="1" placeholder="PMs per Year (Required)" value={equipmentForm.pmsPerYear} onChange={(e) => handleFormChange("pmsPerYear", e.target.value)} />
                <input className="input" type="date" value={equipmentForm.nextPmDate} onChange={(e) => handleFormChange("nextPmDate", e.target.value)} />
                <input className="input" type="date" value={equipmentForm.lastPmDate} onChange={(e) => handleFormChange("lastPmDate", e.target.value)} />
                <input className="input" type="date" value={equipmentForm.completionDate} onChange={(e) => handleFormChange("completionDate", e.target.value)} />
                <input className="input" type="date" aria-label="Contract start date" title="Contract start date" value={equipmentForm.contractStartDate} onChange={(e) => handleFormChange("contractStartDate", e.target.value)} />
                <input className="input" type="date" aria-label="Contract end date" title="Contract end date" value={equipmentForm.contractEndDate} onChange={(e) => handleFormChange("contractEndDate", e.target.value)} />
                <input className="input" placeholder="Reminder dates (comma-separated)" value={equipmentForm.reminderDates} onChange={(e) => handleFormChange("reminderDates", e.target.value)} />
                <select className="select" value={equipmentForm.status} onChange={(e) => handleFormChange("status", e.target.value)}>
                  {editableStatuses.map((status) => (
                    <option key={status} value={status}>
                      {status}
                    </option>
                  ))}
                </select>
                <input className="input" placeholder="Engineer" value={equipmentForm.engineer} onChange={(e) => handleFormChange("engineer", e.target.value)} />
                <input className="input" type="email" placeholder="Hospital Contact Email" value={equipmentForm.contactEmail} onChange={(e) => handleFormChange("contactEmail", e.target.value)} />
                <input className="input" placeholder="Updated by" value={equipmentForm.updatedBy} onChange={(e) => handleFormChange("updatedBy", e.target.value)} />
              </div>
              {editingPmSummary ? (
                <div className="bulk-add-wrap">
                  <div className="strong">PM Status Snapshot</div>
                  <div className="muted">
                    Completed: {editingPmSummary.completedPmCount} / Required: {editingPmSummary.requiredPmCount}
                  </div>
                  <div className="bulk-preview-list">
                    <div className="bulk-preview-item"><span className="strong">PM1:</span> {editingPmSummary.pm1}</div>
                    <div className="bulk-preview-item"><span className="strong">PM2:</span> {editingPmSummary.pm2}</div>
                    <div className="bulk-preview-item"><span className="strong">PM3:</span> {editingPmSummary.pm3}</div>
                    <div className="bulk-preview-item"><span className="strong">Other PM:</span> {editingPmSummary.otherPm}</div>
                  </div>
                </div>
              ) : null}
              {!editingId ? (
                <div className="bulk-add-wrap">
                  <div className="strong">Bulk equipment add for this hospital + contract</div>
                  <div className="muted">
                    Enter one item per line using either <strong>Equipment | Serial | Model | Department</strong> or comma-separated format.
                    Contract dates, PM dates, and contact details from this form are applied to all listed equipment.
                  </div>
                  <textarea
                    className="input textarea bulk-add-textarea"
                    placeholder={"Patient Monitor | MLH-PM-009 | B105 | ICU\nDefibrillator, DEF-544, Lifepak 20, ER"}
                    value={bulkEquipmentText}
                    onChange={(e) => setBulkEquipmentText(e.target.value)}
                  />
                  {parsedBulkItems.length ? (
                    <div className="bulk-preview">
                      <div className="muted">{parsedBulkItems.length} equipment item(s) ready to add</div>
                      <div className="bulk-preview-list">
                        {parsedBulkItems.map((item, index) => (
                          <div key={`${item.equipment}-${item.serial}-${index}`} className="bulk-preview-item">
                            <div className="strong">{item.equipment}</div>
                            <div className="muted">{item.serial || "No serial"} · {item.model || "No model"} · {item.department || "No department"}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : null}
              <textarea className="input textarea" placeholder="Notes" value={equipmentForm.notes} onChange={(e) => handleFormChange("notes", e.target.value)} />
              <button className="button button-primary" type="submit">
                {editingId ? "Save Changes" : bulkEquipmentText.trim() ? "Add Equipment in Bulk" : "Add Equipment"}
              </button>
            </form>
          </div>
            }
          />
        ) : currentPage === "contract-detail" ? (
          (() => {
            const activeContract = contractRows.find((contract) => contract.id === selectedContractId);
            const activeContractRows = rows.filter(
              (row) =>
                `${row.hospital || ""}::${row.contractNo || ""}` === selectedContractId
            );
            return (
          <ContractDetailView
            contract={activeContract}
            contractRows={activeContractRows}
            addEquipmentDraft={contractEquipmentDraft}
            onAddEquipmentDraftChange={handleContractEquipmentDraftChange}
            onAddEquipmentToContract={handleAddEquipmentToContract}
            onRemoveEquipmentFromContract={handleRemoveEquipmentFromContract}
            onEditEquipment={startEdit}
          />
            );
          })()
        ) : (
          <EquipmentTable
            rows={filteredRows}
            getTrackingMeta={getTrackingMeta}
            badgeClass={badgeClass}
            getPmSlotStatus={getPmSlotStatus}
            onView={setDetailRow}
            onEdit={startEdit}
            onDelete={handleDelete}
            onComplete={markComplete}
          />
        )}
      </div>

      <EquipmentDetailModal row={detailRow} onClose={() => setDetailRow(null)} />
    </div>
  );
}
