import React from "react";
import { Download, FileUp } from "lucide-react";

export default function ImportExportBar({ fileInputRef, onImportChange, onExportCsv, onExportJson }) {
  return (
    <div className="actions actions-friendly">
      <input ref={fileInputRef} type="file" accept=".csv,.xlsx,.xls,.json" className="hidden-input" onChange={onImportChange} />
      <button className="button button-soft" onClick={() => fileInputRef.current?.click()}>
        <FileUp size={15} className="inline-icon" />
        Import CSV/Excel/JSON
      </button>
      <button className="button button-soft" onClick={onExportCsv}>
        <Download size={15} className="inline-icon" />
        Export CSV
      </button>
      <button className="button button-soft" onClick={onExportJson}>
        <Download size={15} className="inline-icon" />
        Export JSON
      </button>
    </div>
  );
}
