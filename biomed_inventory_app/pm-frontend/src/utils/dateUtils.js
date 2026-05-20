export function getTodayIsoDate() {
  return new Date().toISOString().slice(0, 10);
}

export function getDaysUntil(dateString) {
  if (!dateString) return Number.POSITIVE_INFINITY;
  const today = new Date(getTodayIsoDate());
  const target = new Date(dateString);
  if (Number.isNaN(target.getTime())) return Number.POSITIVE_INFINITY;
  return Math.ceil((target - today) / (1000 * 60 * 60 * 24));
}

export function addMonths(dateString, months) {
  const base = dateString ? new Date(dateString) : new Date();
  if (Number.isNaN(base.getTime())) return getTodayIsoDate();
  base.setMonth(base.getMonth() + Number(months || 0));
  return base.toISOString().slice(0, 10);
}

export function getIntervalMonths(pmsPerYear) {
  return Math.max(1, Math.round(12 / (Number(pmsPerYear) || 1)));
}

export function isDueThisMonth(dateString) {
  if (!dateString) return false;
  const now = new Date();
  const target = new Date(dateString);
  if (Number.isNaN(target.getTime())) return false;
  return now.getFullYear() === target.getFullYear() && now.getMonth() === target.getMonth();
}

export function getTrackingMeta(row) {
  const daysUntil = getDaysUntil(row.nextPmDate);
  const isCompleted = row.status === 'Completed';
  const isOverdue = !isCompleted && daysUntil < 0;
  const dueSoon7 = !isCompleted && daysUntil >= 0 && daysUntil <= 7;
  const dueSoon14 = !isCompleted && daysUntil >= 0 && daysUntil <= 14;
  const intervalMonths = getIntervalMonths(row.pmsPerYear);
  let effectiveStatus = row.status || 'Upcoming';
  if (isCompleted) effectiveStatus = 'Completed';
  else if (isOverdue) effectiveStatus = 'Overdue';
  else if (dueSoon7) effectiveStatus = 'Due soon';
  return { daysUntil, isOverdue, dueSoon7, dueSoon14, intervalMonths, effectiveStatus };
}
