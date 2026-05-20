const STORAGE_KEY = 'cmm_erp_pm_rows_v1';

export async function loadRowsFromStorage() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (error) {
    console.error('Failed to parse PM local storage', error);
    return null;
  }
}

export async function saveRowsToStorage(rows) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(rows || []));
}
