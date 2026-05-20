import { MAX_PM_PLACEHOLDERS } from "./storage";

function csvBoolean(value, fallback = "") {
  const normalized = String(value || fallback).toLowerCase();
  return normalized === "true" || normalized === "yes";
}

export function parseCsvLine(line) {
  const values = [];
  let current = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    const next = line[i + 1];

    if (char === '"') {
      if (inQuotes && next === '"') {
        current += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }

    if (char === "," && !inQuotes) {
      values.push(current.trim());
      current = "";
      continue;
    }

    current += char;
  }

  values.push(current.trim());
  return values;
}

export function parseCsvText(text) {
  const lines = text.split(/\r?\n/).filter(Boolean);
  if (lines.length < 2) return [];

  const headers = parseCsvLine(lines[0]).map((h) => h.replace(/^\uFEFF/, "").trim());
  return lines.slice(1).map((line) => {
    const values = parseCsvLine(line);
    const obj = {};
    headers.forEach((header, i) => {
      obj[header] = (values[i] || "").trim();
    });
    return obj;
  });
}

export async function parseImportFile(file) {
  const extension = (file.name.split(".").pop() || "").toLowerCase();
  const text = await file.text();

  if (extension === "csv") return parseCsvText(text);

  if (["xlsx", "xls"].includes(extension)) {
    const trimmed = text.trim();
    if (!trimmed) return [];

    // Browser-local fallback for tab-delimited or SpreadsheetML text exports.
    if (trimmed.includes("\t") && trimmed.includes("\n")) {
      const lines = trimmed.split(/\r?\n/).filter(Boolean);
      const headers = lines[0].split("\t").map((item) => item.trim());
      return lines.slice(1).map((line) => {
        const values = line.split("\t");
        const row = {};
        headers.forEach((header, index) => {
          row[header] = (values[index] || "").trim();
        });
        return row;
      });
    }

    if (trimmed.startsWith("<?xml") || trimmed.includes("<Workbook")) {
      const parser = new DOMParser();
      const xml = parser.parseFromString(trimmed, "text/xml");
      const rows = Array.from(xml.querySelectorAll("Row"));
      if (!rows.length) return [];
      const headers = Array.from(rows[0].querySelectorAll("Cell Data")).map((cell) => cell.textContent?.trim() || "");
      return rows.slice(1).map((xmlRow) => {
        const cells = Array.from(xmlRow.querySelectorAll("Cell Data")).map((cell) => cell.textContent?.trim() || "");
        const row = {};
        headers.forEach((header, index) => {
          row[header] = cells[index] || "";
        });
        return row;
      });
    }

    throw new Error("Excel binary files are supported in desktop mode. In browser mode, save as CSV and import.");
  }

  return [];
}

export function normalizeImportedRows(rawRows, normalizeStatus, getTodayIsoDate) {
  return rawRows
    .map((row, index) => {
      const hospital = row.Hospital || row.hospital || row["Parent System"] || row["parent system"] || "";
      const contractNo = row["Contract No."] || row.contractNo || row["Contract Number"] || "";
      const equipment =
        row.Equipment || row.equipment || row.Subsystem || row.subsystem || row["Source Description"] || "";
      const model = row.Model || row.model || "";
      const serial = row["Serial Number"] || row.serial || row.Serial || "";
      const intervalMonths = Number(row["Interval Months"] || row.intervalMonths || 0) || 0;
      const pmsPerYear =
        Number(row["PMs per Year"] || row.pmsPerYear || 0) ||
        (intervalMonths > 0 ? Math.max(1, Math.round(12 / intervalMonths)) : 1);
      const nextPmDate = row["Next PM Date"] || row.nextPmDate || getTodayIsoDate();
      const status = normalizeStatus(row.Status || row.status || "Upcoming");
      const contractStartDate = row["Contract Start Date"] || row.contractStartDate || "";
      const contractEndDate = row["Contract End Date"] || row.contractEndDate || "";
      const engineer = row["Engineer Assigned"] || row.engineer || "";
      const contactEmail = row["Hospital Contact Email"] || row.contactEmail || "";
      const department = row.Department || row.department || "";
      const notes = row.Notes || row.notes || "";
      const reminderDates = row["Reminder Dates"] || row.reminderDates || "";
      const lastPmDate = row["Last PM Date"] || row.lastPmDate || "";
      const completionDate = row["Completion Date"] || row.completionDate || "";
      const createdDate = row["Created Date"] || row.createdDate || getTodayIsoDate();
      const updatedDate = row["Updated Date"] || row.updatedDate || createdDate;
      const updatedBy = row["Updated By"] || row.updatedBy || row.engineer || "System";
      const pmPlaceholders = Object.fromEntries(
        Array.from({ length: MAX_PM_PLACEHOLDERS }, (_, slotIndex) => {
          const slot = slotIndex + 1;
          const value = row[`PM${slot}`] || row[`pm${slot}`] || row[`PM ${slot}`] || "";
          return [`pm${slot}Placeholder`, value];
        })
      );

      if (!hospital && !equipment && !serial) return null;

      return {
        id: Date.now() + index,
        hospital,
        contractNo,
        equipment,
        model,
        serial,
        pmsPerYear,
        nextPmDate,
        department,
        notes,
        reminderDates,
        lastPmDate,
        completionDate,
        status,
        contractStartDate,
        contractEndDate,
        engineer,
        contactEmail,
        reminder1Sent: csvBoolean(row["Reminder 1 Sent"] || row.reminder1Sent, row["Reminder 1 Sent"]),
        reminder2Sent: csvBoolean(row["Reminder 2 Sent"] || row.reminder2Sent, row["Reminder 2 Sent"]),
        engineerAlertSent: csvBoolean(
          row["Engineer Alert Sent"] || row.engineerAlertSent,
          row["Engineer Alert Sent"]
        ),
        createdDate,
        updatedDate,
        updatedBy,
        ...pmPlaceholders,
        pmHistory: [],
        comments: [],
        emailHistory: [],
      };
    })
    .filter(Boolean);
}

export function exportRowsToCsv(rows, getIntervalMonths) {
  const headers = [
    "Hospital",
    "Contract No.",
    "Equipment",
    "Model",
    "Serial Number",
    "PMs per Year",
    "Interval Months",
    "Next PM Date",
    "Department",
    "Notes",
    "Reminder Dates",
    "Last PM Date",
    "Completion Date",
    "Status",
    "Contract Start Date",
    "Contract End Date",
    "Engineer Assigned",
    "Hospital Contact Email",
    "Reminder 1 Sent",
    "Reminder 2 Sent",
    "Engineer Alert Sent",
    "Created Date",
    "Updated Date",
    "Updated By",
    ...Array.from({ length: MAX_PM_PLACEHOLDERS }, (_, index) => `PM${index + 1}`),
  ];

  const csv = [headers.join(",")]
    .concat(
      rows.map((row) =>
        [
          row.hospital,
          row.contractNo,
          row.equipment,
          row.model,
          row.serial,
          row.pmsPerYear,
          getIntervalMonths(row.pmsPerYear),
          row.nextPmDate,
          row.department,
          row.notes,
          row.reminderDates,
          row.lastPmDate,
          row.completionDate,
          row.status,
          row.contractStartDate,
          row.contractEndDate,
          row.engineer,
          row.contactEmail,
          row.reminder1Sent ? "Yes" : "No",
          row.reminder2Sent ? "Yes" : "No",
          row.engineerAlertSent ? "Yes" : "No",
          row.createdDate,
          row.updatedDate,
          row.updatedBy,
          ...Array.from(
            { length: MAX_PM_PLACEHOLDERS },
            (_, index) => row[`pm${index + 1}Placeholder`] || ""
          ),
        ]
          .map((value) => `"${String(value ?? "").replace(/"/g, '""')}"`)
          .join(",")
      )
    )
    .join("\n");

  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "pm-tracker-export.csv";
  a.click();
  URL.revokeObjectURL(url);
}
