const STORAGE_KEY = 'cmm_erp_pm_rows_v1';
const DB_NAME = 'cmm_erp_pm_tracker';
const DB_VERSION = 1;
const STORE_NAME = 'pm_rows';
const ROWS_ID = 'rows';

function readLocalStorageBackup() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (error) {
    console.error('Failed to parse PM local storage backup', error);
    return null;
  }
}

function saveLocalStorageBackup(rows) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(rows || []));
}

function openRowsDb() {
  if (!('indexedDB' in window)) {
    return Promise.reject(new Error('IndexedDB is not available in this browser.'));
  }

  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id' });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function runStoreTransaction(mode, callback) {
  return openRowsDb().then(
    (db) =>
      new Promise((resolve, reject) => {
        const transaction = db.transaction(STORE_NAME, mode);
        const store = transaction.objectStore(STORE_NAME);
        const request = callback(store);

        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
        transaction.oncomplete = () => db.close();
        transaction.onerror = () => {
          db.close();
          reject(transaction.error);
        };
      })
  );
}

export async function loadRowsFromStorage() {
  try {
    const record = await runStoreTransaction('readonly', (store) => store.get(ROWS_ID));
    if (record?.rows) return record.rows;
  } catch (error) {
    console.error('Failed to load PM rows from IndexedDB; using localStorage backup', error);
  }

  return readLocalStorageBackup();
}

export async function saveRowsToStorage(rows) {
  saveLocalStorageBackup(rows);
  await runStoreTransaction('readwrite', (store) =>
    store.put({ id: ROWS_ID, rows: rows || [], updatedAt: new Date().toISOString() })
  );
}
