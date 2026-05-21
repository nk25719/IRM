import * as XLSX from 'xlsx';
import { MAX_PM_PLACEHOLDERS } from './storage.js';

function toCsvCell(value) {
  return `"${String(value ?? '').replace(/"/g, '""')}"`;
}

export function parseCsvText(text) {
  const rows = [];
  let row = [];
  let cell = '';
  let inQuotes = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const nextChar = text[index + 1];

    if (char === '"') {
      if (inQuotes && nextChar === '"') {
        cell += '"';
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }

    if (char === ',' && !inQuotes) {
      row.push(cell);
      cell = '';
      continue;
    }

    if ((char === '\n' || char === '\r') && !inQuotes) {
      if (char === '\r' && nextChar === '\n') index += 1;
      row.push(cell);
      if (row.some((value) => value.trim())) rows.push(row);
      row = [];
      cell = '';
      continue;
    }

    cell += char;
  }

  row.push(cell);
  if (row.some((value) => value.trim())) rows.push(row);
  if (!rows.length) return [];

  const headers = rows[0].map((header) => header.trim());
  return rows.slice(1).map((values) =>
    headers.reduce((record, header, index) => {
      record[header] = values[index] ?? '';
      return record;
    }, {})
  );
}

export function exportRowsToCsv(rows, getIntervalMonths) {
  const headers = [
    'Hospital', 'Contract No.', 'Equipment', 'Model', 'Serial', 'Department', 'PMs per Year',
    'Interval Months', 'Next PM Date', 'Last PM Date', 'Completion Date', 'Status', 'Engineer',
    'Contact Email', 'Notes', 'Contract Start Date', 'Contract End Date'
  ];
  const csv = [headers.join(',')]
    .concat((rows || []).map((row) => [
      row.hospital,
      row.contractNo,
      row.equipment,
      row.model,
      row.serial,
      row.department,
      row.pmsPerYear,
      getIntervalMonths ? getIntervalMonths(row.pmsPerYear) : '',
      row.nextPmDate,
      row.lastPmDate,
      row.completionDate,
      row.status,
      row.engineer,
      row.contactEmail,
      row.notes,
      row.contractStartDate,
      row.contractEndDate,
    ].map(toCsvCell).join(',')))
    .join('\n');

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'pm-equipment-export.csv';
  anchor.click();
  URL.revokeObjectURL(url);
}

export function exportRowsToJson(rows) {
  const blob = new Blob([JSON.stringify(rows || [], null, 2)], { type: 'application/json;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'pm-equipment-backup.json';
  anchor.click();
  URL.revokeObjectURL(url);
}

export async function parseImportFile(file) {
  if (file.name.toLowerCase().endsWith('.json') || file.type === 'application/json') {
    const parsed = JSON.parse(await file.text());
    return Array.isArray(parsed) ? parsed : parsed.rows || [];
  }

  if (file.name.toLowerCase().endsWith('.csv') || file.type === 'text/csv') {
    return parseCsvText(await file.text());
  }

  const buffer = await file.arrayBuffer();
  const workbook = XLSX.read(buffer, { type: 'array' });
  const sheet = workbook.Sheets[workbook.SheetNames[0]];
  return XLSX.utils.sheet_to_json(sheet, { defval: '' });
}

function collectPmPlaceholderFields(row) {
  return Object.fromEntries(
    Array.from({ length: MAX_PM_PLACEHOLDERS }, (_, index) => {
      const slot = index + 1;
      const value =
        row[`PM${slot}`] ||
        row[`PM ${slot}`] ||
        row[`PM${slot} Placeholder`] ||
        row[`PM ${slot} Placeholder`] ||
        row[`pm${slot}`] ||
        row[`pm${slot}Placeholder`] ||
        '';
      return [`pm${slot}Placeholder`, String(value || '').trim()];
    })
  );
}

export function normalizeImportedRows(rawRows, normalizeStatus, getTodayIsoDate) {
  const today = getTodayIsoDate ? getTodayIsoDate() : new Date().toISOString().slice(0, 10);
  return (rawRows || []).map((row, index) => ({
    id: Date.now() + index,
    hospital: row.Hospital || row.hospital || '',
    contractNo: row['Contract No.'] || row.contractNo || row['Contract Number'] || '',
    equipment: row.Equipment || row.equipment || '',
    model: row.Model || row.model || '',
    serial: row.Serial || row.serial || row['Serial Number'] || row.serialNumber || '',
    department: row.Department || row.department || '',
    pmsPerYear: Math.max(1, Number(row['PMs per Year'] || row.pmsPerYear || 1) || 1),
    nextPmDate: row['Next PM Date'] || row.nextPmDate || '',
    lastPmDate: row['Last PM Date'] || row.lastPmDate || '',
    completionDate: row['Completion Date'] || row.completionDate || '',
    contractStartDate: row['Contract Start Date'] || row.contractStartDate || '',
    contractEndDate: row['Contract End Date'] || row.contractEndDate || '',
    reminderDates: row['Reminder Dates'] || row.reminderDates || '',
    status: normalizeStatus ? normalizeStatus(row.Status || row.status) : row.Status || row.status || 'Upcoming',
    engineer: row.Engineer || row.engineer || row['Engineer Assigned'] || row.engineerAssigned || '',
    contactEmail: row['Contact Email'] || row.contactEmail || row['Hospital Contact Email'] || row.hospitalContactEmail || '',
    notes: row.Notes || row.notes || '',
    createdDate: today,
    updatedDate: today,
    updatedBy: row['Updated By'] || row.updatedBy || 'Import',
    reminder1Sent: false,
    reminder2Sent: false,
    engineerAlertSent: false,
    pmHistory: [],
    contractHistory: [],
    ...collectPmPlaceholderFields(row),
  })).filter((row) => row.hospital || row.equipment || row.contractNo);
}
