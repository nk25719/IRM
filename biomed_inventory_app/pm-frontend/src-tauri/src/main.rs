#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use chrono::Utc;
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use tauri::Manager;

#[derive(Debug, Serialize, Deserialize)]
struct BackupResult {
    path: String,
}

#[tauri::command]
fn init_sqlite(app_handle: tauri::AppHandle) -> Result<String, String> {
    let app_dir = app_handle
        .path()
        .app_data_dir()
        .map_err(|e| format!("Failed to resolve app data directory: {e}"))?;
    fs::create_dir_all(&app_dir).map_err(|e| format!("Failed to create app data directory: {e}"))?;

    let db_path = app_dir.join("pm_tracker.db");
    let conn = Connection::open(&db_path).map_err(|e| format!("Failed to open database: {e}"))?;

    conn.execute_batch(
        "
      CREATE TABLE IF NOT EXISTS equipment_records (
        id INTEGER PRIMARY KEY,
        payload_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS audit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        equipment_id INTEGER,
        event_type TEXT NOT NULL,
        payload_json TEXT,
        created_at TEXT NOT NULL
      );
      ",
    )
    .map_err(|e| format!("Failed to create database schema: {e}"))?;

    Ok(db_path.to_string_lossy().to_string())
}

#[tauri::command]
fn save_equipment_snapshot(app_handle: tauri::AppHandle, payload_json: String) -> Result<(), String> {
    let app_dir = app_handle
        .path()
        .app_data_dir()
        .map_err(|e| format!("Failed to resolve app data directory: {e}"))?;
    let db_path = app_dir.join("pm_tracker.db");
    let conn = Connection::open(&db_path).map_err(|e| format!("Failed to open database: {e}"))?;

    conn.execute(
        "INSERT OR REPLACE INTO equipment_records(id, payload_json, updated_at) VALUES (1, ?1, ?2)",
        params![payload_json, Utc::now().to_rfc3339()],
    )
    .map_err(|e| format!("Failed to save snapshot: {e}"))?;

    Ok(())
}

#[tauri::command]
fn create_local_backup(app_handle: tauri::AppHandle) -> Result<BackupResult, String> {
    let app_dir = app_handle
        .path()
        .app_data_dir()
        .map_err(|e| format!("Failed to resolve app data directory: {e}"))?;
    let db_path = app_dir.join("pm_tracker.db");

    let backup_dir: PathBuf = app_dir.join("backups");
    fs::create_dir_all(&backup_dir).map_err(|e| format!("Failed to create backup directory: {e}"))?;

    let backup_file = backup_dir.join(format!("backup-{}.db", Utc::now().format("%Y%m%d-%H%M%S")));
    fs::copy(&db_path, &backup_file).map_err(|e| format!("Failed to create backup: {e}"))?;

    Ok(BackupResult {
        path: backup_file.to_string_lossy().to_string(),
    })
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .invoke_handler(tauri::generate_handler![
            init_sqlite,
            save_equipment_snapshot,
            create_local_backup
        ])
        .setup(|app| {
            let _ = init_sqlite(app.handle().clone());
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running PM Tracker desktop app");
}
