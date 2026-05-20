# Private Long-Term Version Plan

## Decision: Browser-local vs Desktop

**Decision made:** move to **desktop app (Tauri)** for long-term private use.

### Why desktop is better for this PM tracker
- Better control of local private data and backup folders.
- Native SQLite reliability for long-term record retention.
- Easier offline operation in hospitals with limited internet.
- Cleaner packaging/distribution for internal teams.

## What has been started in this repository

1. **Tauri desktop scaffold created**
   - `src-tauri/tauri.conf.json`
   - `src-tauri/Cargo.toml`
   - `src-tauri/src/main.rs`

2. **SQLite initialization added**
   - Desktop command `init_sqlite` creates:
     - `equipment_records`
     - `audit_events`

3. **Local backup folder support**
   - Desktop command `create_local_backup` copies DB snapshots to app data `backups/`.

4. **CSV/Excel import support added in UI**
   - Browser app now accepts `.csv`, `.xlsx`, `.xls` import.

## Next implementation steps

1. Replace IndexedDB adapter with a storage abstraction that can switch between:
   - Browser IndexedDB mode
   - Desktop SQLite mode
2. Add explicit import mapping preview for Excel/CSV headers.
3. Add scheduled backup policy (daily/weekly) and backup retention rules.
4. Encrypt sensitive local fields (hospital contacts, email logs).
5. Add per-user activity trail for compliance.
