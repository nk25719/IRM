const DB_NAME = "pm-tracker-db";
const DB_VERSION = 1;
const STORE_NAME = "state";
const ROWS_KEY = "rows";

export const LEGACY_STORAGE_KEY = "pm-tracker-rows";

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME);
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function getFromIndexedDb(key) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, "readonly");
    const store = transaction.objectStore(STORE_NAME);
    const request = store.get(key);

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function setInIndexedDb(key, value) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, "readwrite");
    const store = transaction.objectStore(STORE_NAME);
    store.put(value, key);

    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error);
  });
}

function readLegacyRows() {
  try {
    const raw = localStorage.getItem(LEGACY_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeLegacyBackup(rows) {
  try {
    localStorage.setItem(LEGACY_STORAGE_KEY, JSON.stringify(rows));
  } catch {
    // Ignore quota/write errors for backup storage.
  }
}

export async function loadRowsFromStorage() {
  const indexedRows = await getFromIndexedDb(ROWS_KEY);
  if (Array.isArray(indexedRows)) {
    return indexedRows;
  }

  const legacyRows = readLegacyRows();
  if (Array.isArray(legacyRows)) {
    await setInIndexedDb(ROWS_KEY, legacyRows);
    return legacyRows;
  }

  return null;
}

export async function saveRowsToStorage(rows) {
  await setInIndexedDb(ROWS_KEY, rows);
  writeLegacyBackup(rows);
}
