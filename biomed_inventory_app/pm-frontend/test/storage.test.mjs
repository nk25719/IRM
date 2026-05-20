import test from "node:test";
import assert from "node:assert/strict";
import { loadRowsFromStorage, saveRowsToStorage, LEGACY_STORAGE_KEY } from "../src/storage.js";

function createLocalStorageMock() {
  const store = new Map();
  return {
    getItem(key) {
      return store.has(key) ? store.get(key) : null;
    },
    setItem(key, value) {
      store.set(key, String(value));
    },
    removeItem(key) {
      store.delete(key);
    },
    clear() {
      store.clear();
    },
  };
}

function createIndexedDbMock() {
  const databases = new Map();

  class IDBDatabaseMock {
    constructor(name) {
      this.name = name;
      this._stores = databases.get(name) || new Map();
      databases.set(name, this._stores);
      this.objectStoreNames = {
        contains: (storeName) => this._stores.has(storeName),
      };
    }

    createObjectStore(storeName) {
      if (!this._stores.has(storeName)) {
        this._stores.set(storeName, new Map());
      }
    }

    transaction(storeName, mode) {
      if (!this._stores.has(storeName)) {
        this._stores.set(storeName, new Map());
      }

      const store = this._stores.get(storeName);
      const transaction = {
        error: null,
        oncomplete: null,
        onerror: null,
        onabort: null,
        objectStore() {
          return {
            get(key) {
              const request = { onsuccess: null, onerror: null, result: undefined, error: null };
              setTimeout(() => {
                request.result = store.get(key);
                request.onsuccess?.({ target: request });
              }, 0);
              return request;
            },
            put(value, key) {
              store.set(key, value);
              if (mode === "readwrite") {
                setTimeout(() => transaction.oncomplete?.(), 0);
              }
              return { onsuccess: null, onerror: null };
            },
          };
        },
      };

      return transaction;
    }
  }

  return {
    open(name) {
      const request = { onsuccess: null, onerror: null, onupgradeneeded: null, result: null, error: null };
      setTimeout(() => {
        const isNew = !databases.has(name);
        const db = new IDBDatabaseMock(name);
        request.result = db;

        if (isNew) {
          request.onupgradeneeded?.({ target: request });
        }

        request.onsuccess?.({ target: request });
      }, 0);
      return request;
    },
  };
}

function makeRows(count) {
  return Array.from({ length: count }, (_, index) => ({
    id: index + 1,
    hospital: `Hospital ${index + 1}`,
    contractNo: `SC/${index}`,
    equipment: "Patient Monitor",
    model: "Model-X",
    serial: `SN-${index}`,
    pmsPerYear: 4,
    nextPmDate: "2026-12-01",
    department: "ICU",
    notes: "Load test row",
    reminderDates: "2026-11-15,2026-11-22",
    lastPmDate: "2026-09-01",
    completionDate: "",
    status: "Upcoming",
    engineer: "Test Engineer",
    contactEmail: "test@example.com",
    reminder1Sent: false,
    reminder2Sent: false,
    engineerAlertSent: false,
  }));
}

test.beforeEach(() => {
  global.localStorage = createLocalStorageMock();
  global.indexedDB = createIndexedDbMock();
});

test("migrates legacy localStorage data into IndexedDB", async () => {
  const legacyRows = makeRows(3);
  localStorage.setItem(LEGACY_STORAGE_KEY, JSON.stringify(legacyRows));

  const firstLoad = await loadRowsFromStorage();
  assert.equal(firstLoad.length, 3);
  assert.equal(firstLoad[0].hospital, "Hospital 1");

  localStorage.removeItem(LEGACY_STORAGE_KEY);
  const secondLoad = await loadRowsFromStorage();
  assert.equal(secondLoad.length, 3);
  assert.equal(secondLoad[2].hospital, "Hospital 3");
});

test("saves and reloads larger datasets from IndexedDB with localStorage backup", async () => {
  const largeRows = makeRows(5000);

  await saveRowsToStorage(largeRows);

  const legacyBackup = JSON.parse(localStorage.getItem(LEGACY_STORAGE_KEY));
  assert.equal(legacyBackup.length, 5000);

  localStorage.clear();

  const reloadedRows = await loadRowsFromStorage();
  assert.equal(reloadedRows.length, 5000);
  assert.equal(reloadedRows[4999].hospital, "Hospital 5000");
});
