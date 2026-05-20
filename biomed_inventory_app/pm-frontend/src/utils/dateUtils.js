export function getTodayIsoDate() {
  return new Date().toISOString().slice(0, 10);
}

export function getDaysUntil(dateStr) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(dateStr);
  target.setHours(0, 0, 0, 0);
  return Math.round((target - today) / (1000 * 60 * 60 * 24));
}

export function isDueThisMonth(dateStr) {
  const target = new Date(dateStr);
  const today = new Date();
  return target.getFullYear() === today.getFullYear() && target.getMonth() === today.getMonth();
}

export function getIntervalMonths(pmsPerYear) {
  const count = Number(pmsPerYear) || 1;
  return Number((12 / count).toFixed(2));
}

export function addMonths(dateStr, months) {
  if (!dateStr) return "";
  const base = new Date(dateStr);
  if (Number.isNaN(base.getTime())) return "";
  const out = new Date(base);
  out.setMonth(out.getMonth() + months);
  return out.toISOString().slice(0, 10);
}

export function getTrackingMeta(row) {
  const status = row.status || "Upcoming";
  const daysUntil = getDaysUntil(row.nextPmDate);
  const isDoneState = status === "Completed" || status === "Deferred";
  const isOverdue = !isDoneState && daysUntil < 0;
  const dueSoon7 = !isDoneState && daysUntil >= 0 && daysUntil <= 7;
  const dueSoon14 = !isDoneState && daysUntil >= 0 && daysUntil <= 14;

  return {
    daysUntil,
    isOverdue,
    dueSoon7,
    dueSoon14,
    intervalMonths: getIntervalMonths(row.pmsPerYear),
    effectiveStatus: isOverdue ? "Overdue" : status,
  };
}
