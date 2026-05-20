import { getTodayIsoDate } from "./dateUtils";

export const MAX_PM_PLACEHOLDERS = 30;

export const statuses = [
  "All",
  "Upcoming",
  "Hospital notified",
  "Confirmed",
  "In progress",
  "Completed",
  "Overdue",
  "Deferred",
];

export const editableStatuses = statuses.filter((status) => !["All", "Overdue"].includes(status));

export function normalizeStatus(status) {
  if (status === "Overdue") return "Upcoming";
  return editableStatuses.includes(status) ? status : "Upcoming";
}

function normalizePmHistory(row) {
  if (Array.isArray(row.pmHistory)) return row.pmHistory;

  const history = [];
  if (row.lastPmDate) {
    history.push({
      date: row.lastPmDate,
      status: "Completed",
      notes: "Legacy PM entry",
      updatedBy: row.updatedBy || row.engineer || "System",
    });
  }
  if (row.completionDate && row.completionDate !== row.lastPmDate) {
    history.push({
      date: row.completionDate,
      status: "Completed",
      notes: "Completion entry",
      updatedBy: row.updatedBy || row.engineer || "System",
    });
  }
  return history;
}

function normalizeContractHistory(row) {
  if (Array.isArray(row.contractHistory)) return row.contractHistory;
  if (!row.contractNo && !row.contractStartDate && !row.contractEndDate) return [];
  return [
    {
      at: row.updatedDate || row.createdDate || getTodayIsoDate(),
      by: row.updatedBy || row.engineer || "System",
      note: `Contract linked (${row.contractNo || "No contract #"})`,
      contractNo: row.contractNo || "",
      contractStartDate: row.contractStartDate || "",
      contractEndDate: row.contractEndDate || "",
    },
  ];
}

export function normalizeRows(rows) {
  const today = getTodayIsoDate();

  return rows.map((row) => ({
    ...row,
    department: row.department || "",
    notes: row.notes || "",
    reminderDates: row.reminderDates || "",
    lastPmDate: row.lastPmDate || "",
    completionDate: row.completionDate || "",
    createdDate: row.createdDate || today,
    updatedDate: row.updatedDate || row.createdDate || today,
    updatedBy: row.updatedBy || row.engineer || "System",
    contractStartDate: row.contractStartDate || "",
    contractEndDate: row.contractEndDate || "",
    contractHistory: normalizeContractHistory(row),
    pmHistory: normalizePmHistory(row),
    reminder1Sent: Boolean(row.reminder1Sent),
    reminder2Sent: Boolean(row.reminder2Sent),
    engineerAlertSent: Boolean(row.engineerAlertSent),
    status: normalizeStatus(row.status || "Upcoming"),
    comments: Array.isArray(row.comments) ? row.comments : [],
    emailHistory: Array.isArray(row.emailHistory) ? row.emailHistory : [],
    ...Object.fromEntries(
      Array.from({ length: MAX_PM_PLACEHOLDERS }, (_, index) => {
        const slot = index + 1;
        const key = `pm${slot}Placeholder`;
        return [key, row[key] || ""];
      })
    ),
  }));
}

export function createDefaultEquipmentForm() {
  return {
    hospital: "",
    contractNo: "",
    equipment: "",
    model: "",
    serial: "",
    department: "",
    pmsPerYear: 1,
    nextPmDate: "",
    lastPmDate: "",
    completionDate: "",
    reminderDates: "",
    status: "Upcoming",
    contractStartDate: "",
    contractEndDate: "",
    engineer: "",
    contactEmail: "",
    notes: "",
    updatedBy: "",
    ...Object.fromEntries(
      Array.from({ length: MAX_PM_PLACEHOLDERS }, (_, index) => [`pm${index + 1}Placeholder`, ""])
    ),
  };
}

export function createEquipmentFormFromRow(row) {
  return {
    hospital: row.hospital || "",
    contractNo: row.contractNo || "",
    equipment: row.equipment || "",
    model: row.model || "",
    serial: row.serial || "",
    department: row.department || "",
    pmsPerYear: row.pmsPerYear || 1,
    nextPmDate: row.nextPmDate || "",
    lastPmDate: row.lastPmDate || "",
    completionDate: row.completionDate || "",
    reminderDates: row.reminderDates || "",
    status: row.status || "Upcoming",
    contractStartDate: row.contractStartDate || "",
    contractEndDate: row.contractEndDate || "",
    engineer: row.engineer || "",
    contactEmail: row.contactEmail || "",
    notes: row.notes || "",
    updatedBy: row.updatedBy || row.engineer || "",
    ...Object.fromEntries(
      Array.from({ length: MAX_PM_PLACEHOLDERS }, (_, index) => {
        const slot = index + 1;
        const key = `pm${slot}Placeholder`;
        return [key, row[key] || ""];
      })
    ),
  };
}
