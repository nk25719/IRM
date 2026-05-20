import * as XLSX from 'xlsx';

function toCsvCell(value) {
  return `"${String(value ?? '').replace(/"/g, '""')}"`;
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

export async function parseImportFile(file) {
  const buffer = await file.arrayBuffer();
  const workbook = XLSX.read(buffer, { type: 'array' });
  const sheet = workbook.Sheets[workbook.SheetNames[0]];
  return XLSX.utils.sheet_to_json(sheet, { defval: '' });
}

export function normalizeImportedRows(rawRows, normalizeStatus, getTodayIsoDate) {
  const today = getTodayIsoDate ? getTodayIsoDate() : new Date().toISOString().slice(0, 10);
  return (rawRows || []).map((row, index) => ({
    id: Date.now() + index,
    hospital: row.Hospital || row.hospital || '',
    contractNo: row['Contract No.'] || row.contractNo || row['Contract Number'] || '',
    equipment: row.Equipment || row.equipment || '',
    model: row.Model || row.model || '',
    serial: row.Serial || row.serial || row['Serial Number'] || '',
    department: row.Department || row.department || '',
    pmsPerYear: Math.max(1, Number(row['PMs per Year'] || row.pmsPerYear || 1) || 1),
    nextPmDate: row['Next PM Date'] || row.nextPmDate || '',
    lastPmDate: row['Last PM Date'] || row.lastPmDate || '',
    completionDate: row['Completion Date'] || row.completionDate || '',
    contractStartDate: row['Contract Start Date'] || row.contractStartDate || '',
    contractEndDate: row['Contract End Date'] || row.contractEndDate || '',
    reminderDates: row['Reminder Dates'] || row.reminderDates || '',
    status: normalizeStatus ? normalizeStatus(row.Status || row.status) : row.Status || row.status || 'Upcoming',
    engineer: row.Engineer || row.engineer || '',
    contactEmail: row['Contact Email'] || row.contactEmail || '',
    notes: row.Notes || row.notes || '',
    createdDate: today,
    updatedDate: today,
    updatedBy: row['Updated By'] || row.updatedBy || 'Import',
    reminder1Sent: false,
    reminder2Sent: false,
    engineerAlertSent: false,
    pmHistory: [],
    contractHistory: [],
  })).filter((row) => row.hospital || row.equipment || row.contractNo);
}
