export const MAX_PM_PLACEHOLDERS = 3;

export const statuses = ['All', 'Upcoming', 'Hospital notified', 'Confirmed', 'Completed', 'Deferred', 'Overdue'];
export const editableStatuses = ['Upcoming', 'Hospital notified', 'Confirmed', 'Completed', 'Deferred'];

export function normalizeStatus(value) {
  const text = String(value || '').trim();
  if (!text) return 'Upcoming';
  const match = editableStatuses.find((status) => status.toLowerCase() === text.toLowerCase());
  return match || text;
}

export function createDefaultEquipmentForm() {
  return {
    hospital: '',
    contractNo: '',
    equipment: '',
    model: '',
    serial: '',
    department: '',
    pmsPerYear: 1,
    nextPmDate: '',
    lastPmDate: '',
    completionDate: '',
    contractStartDate: '',
    contractEndDate: '',
    reminderDates: '',
    status: 'Upcoming',
    engineer: '',
    contactEmail: '',
    updatedBy: '',
    notes: '',
    reminder1Sent: false,
    reminder2Sent: false,
    engineerAlertSent: false,
    pmHistory: [],
    contractHistory: [],
    comments: [],
    emailHistory: [],
    pm1Placeholder: '',
    pm2Placeholder: '',
    pm3Placeholder: '',
  };
}

export function createEquipmentFormFromRow(row) {
  return {
    ...createDefaultEquipmentForm(),
    ...row,
  };
}

export function normalizeRows(rows) {
  return (rows || []).map((row, index) => ({
    ...createDefaultEquipmentForm(),
    ...row,
    id: row.id || Date.now() + index,
    pmsPerYear: Math.max(1, Number(row.pmsPerYear) || 1),
    status: normalizeStatus(row.status),
    reminder1Sent: Boolean(row.reminder1Sent),
    reminder2Sent: Boolean(row.reminder2Sent),
    engineerAlertSent: Boolean(row.engineerAlertSent),
    pmHistory: Array.isArray(row.pmHistory) ? row.pmHistory : [],
    contractHistory: Array.isArray(row.contractHistory) ? row.contractHistory : [],
    comments: Array.isArray(row.comments) ? row.comments : [],
    emailHistory: Array.isArray(row.emailHistory) ? row.emailHistory : [],
  }));
}
