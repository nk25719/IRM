import React from "react";
import { Download, FileUp, MoreHorizontal } from "lucide-react";

export default function ImportExportBar({ fileInputRef, onImportChange, onExportCsv, onExportJson }) {
  return (
    <details className="utility-menu">
      <summary aria-label="Import and export">
        <MoreHorizontal size={18} />
      </summary>
      <div className="utility-popover">
      <input ref={fileInputRef} type="file" accept=".csv,.xlsx,.xls,.json" className="hidden-input" onChange={onImportChange} />
      <button type="button" onClick={() => fileInputRef.current?.click()}>
        <FileUp size={15} className="inline-icon" />
        Import CSV/Excel/JSON
      </button>
      <button type="button" onClick={onExportCsv}>
        <Download size={15} className="inline-icon" />
        Export CSV
      </button>
      <button type="button" onClick={onExportJson}>
        <Download size={15} className="inline-icon" />
        Export JSON
      </button>
      </div>
    </details>
  );
}
