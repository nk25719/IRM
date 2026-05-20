import React, { useMemo, useState } from "react";
import { Bot, Building2, CheckSquare, Copy, Mail, MessageSquare, Square, Wrench } from "lucide-react";

function buildEmailDraft(pendingRows, hospital, useAiTone = false) {
  const subject = `Preventive Maintenance Follow-up - ${hospital} (${pendingRows.length} pending item${pendingRows.length === 1 ? "" : "s"})`;
  const equipmentLines = pendingRows.map(
    (row, index) =>
      `${index + 1}. ${row.equipment} | Model: ${row.model || "-"} | Serial: ${row.serial || "-"} | Dept: ${row.department || "-"} | Status: ${row.status || "Upcoming"} | Next PM: ${row.nextPmDate || "-"}`
  );

  const aiLine = useAiTone
    ? "Please use a concise, customer-friendly tone and keep the request action-oriented."
    : "Please confirm availability so we can finalize the preventive maintenance schedule.";

  const body = [
    "Hello,",
    "",
    `This is a follow-up on pending preventive maintenance for ${hospital}.`,
    aiLine,
    "",
    "Pending equipment and current status:",
    ...equipmentLines,
    "",
    "To help us proceed, please:",
    "1) Confirm equipment availability and preferred access windows.",
    "2) Share any access constraints, permits, or safety requirements.",
    "3) Confirm a contact person for day-of-maintenance coordination.",
    "4) Reply with your preferred dates to schedule each pending item.",
    "",
    "Regards,",
    "PM Team",
  ].join("\n");

  return { subject, body };
}

function buildEngineerDispatchMessage(targetRows, hospital) {
  const lines = targetRows.map(
    (row, index) =>
      `${index + 1}. ${row.equipment} (${row.serial || "No serial"}) - ${row.department || "No department"} - Next PM: ${row.nextPmDate || "N/A"} - Hospital Contact: ${row.contactEmail || "N/A"}`
  );

  return [
    `Engineer dispatch list for ${hospital}`,
    "",
    "Please prepare and send the following PM items:",
    ...lines,
    "",
    "Include parts/tools readiness and propose visit windows per item.",
  ].join("\n");
}

function buildAiPrompt(emailDraft, hospital) {
  return [
    "Rewrite the following PM follow-up email for a hospital customer.",
    "Tone: professional, clear, warm, and concise.",
    "Keep all equipment details accurate and keep numbered action requests.",
    `Hospital: ${hospital}`,
    "",
    "EMAIL TO REWRITE:",
    `Subject: ${emailDraft.subject}`,
    "",
    emailDraft.body,
  ].join("\n");
}

export default function HospitalDetailView({
  hospital,
  rows,
  getTrackingMeta,
  onSendHospitalEmail,
  onAddHospitalComment,
  quickActionFeedback,
}) {
  const [selectedEquipmentIds, setSelectedEquipmentIds] = useState([]);
  const [copied, setCopied] = useState(false);
  const [copiedAiPrompt, setCopiedAiPrompt] = useState(false);
  const [copiedEngineerMessage, setCopiedEngineerMessage] = useState(false);
  const [commentText, setCommentText] = useState("");
  const [commentBy, setCommentBy] = useState("PM Coordinator");
  const [useAiTone, setUseAiTone] = useState(true);
  const [statusFocus, setStatusFocus] = useState("All");
  const [isStatusViewOpen, setIsStatusViewOpen] = useState(false);

  const selectedRows = useMemo(() => {
    if (!selectedEquipmentIds.length) return rows;
    const selectedSet = new Set(selectedEquipmentIds.map((id) => String(id)));
    return rows.filter((row) => selectedSet.has(String(row.id)));
  }, [rows, selectedEquipmentIds]);

  const pendingRows = useMemo(
    () => selectedRows.filter((row) => getTrackingMeta(row).effectiveStatus !== "Completed"),
    [selectedRows, getTrackingMeta]
  );

  const statusSummary = useMemo(() => {
    return selectedRows.reduce(
      (acc, row) => {
        const meta = getTrackingMeta(row);
        const normalizedStatus = String(meta.effectiveStatus || "").toLowerCase();
        if (normalizedStatus === "completed") acc.completed += 1;
        else acc.pending += 1;

        if (meta.isOverdue) acc.overdue += 1;
        if (meta.dueSoon7) acc.dueSoon7 += 1;
        if (meta.dueSoon14) acc.dueSoon14 += 1;
        return acc;
      },
      { pending: 0, completed: 0, overdue: 0, dueSoon7: 0, dueSoon14: 0 }
    );
  }, [selectedRows, getTrackingMeta]);

  const averageResponseHours = useMemo(() => {
    const responseHourSamples = selectedRows.flatMap((row) =>
      (row.emailHistory || [])
        .map((entry) => Number(entry.responseHours))
        .filter((value) => Number.isFinite(value) && value >= 0)
    );
    if (!responseHourSamples.length) return null;
    const total = responseHourSamples.reduce((sum, value) => sum + value, 0);
    return Math.round((total / responseHourSamples.length) * 10) / 10;
  }, [selectedRows]);

  const selectedEquipment = useMemo(
    () => (selectedRows.length === 1 ? selectedRows[0] : null),
    [selectedRows]
  );

  const allSelected = selectedEquipmentIds.length === rows.length && rows.length > 0;
  const selectionLabel = selectedEquipmentIds.length
    ? `${selectedEquipmentIds.length} manually selected`
    : "All equipment selected";

  const emailDraft = pendingRows.length ? buildEmailDraft(pendingRows, hospital, useAiTone) : null;
  const generatedEmailText = emailDraft ? `Subject: ${emailDraft.subject}\n\n${emailDraft.body}` : "";
  const canEmailSelected = pendingRows.length > 0;
  const selectedMailTo = canEmailSelected
    ? `mailto:${Array.from(new Set(pendingRows.map((row) => row.contactEmail).filter(Boolean))).join(",")}?subject=${encodeURIComponent(emailDraft.subject)}&body=${encodeURIComponent(emailDraft.body)}`
    : "";

  const engineerDispatchMessage = useMemo(
    () => buildEngineerDispatchMessage(pendingRows, hospital),
    [pendingRows, hospital]
  );

  const communicationTimeline = useMemo(() => {
    return selectedRows
      .flatMap((row) => [
        ...(row.comments || []).map((item) => ({
          ...item,
          type: "comment",
          equipment: row.equipment,
          serial: row.serial,
        })),
        ...(row.emailHistory || []).map((item) => ({
          ...item,
          type: "email",
          equipment: row.equipment,
          serial: row.serial,
        })),
        ...(row.pmHistory || []).map((item) => ({
          ...item,
          type: "pm",
          equipment: row.equipment,
          serial: row.serial,
        })),
        ...(row.contractHistory || []).map((item) => ({
          ...item,
          type: "contract",
          equipment: row.equipment,
          serial: row.serial,
        })),
      ])
      .sort((a, b) => new Date(b.at || b.date || 0) - new Date(a.at || a.date || 0));
  }, [selectedRows]);

  const displayedRows = useMemo(() => {
    if (statusFocus === "All") return selectedRows;
    return selectedRows.filter((row) => {
      const meta = getTrackingMeta(row);
      if (statusFocus === "Overdue") return meta.isOverdue && meta.effectiveStatus !== "Completed";
      if (statusFocus === "DueSoon") {
        return (meta.dueSoon7 || meta.dueSoon14) && meta.effectiveStatus !== "Completed";
      }
      if (statusFocus === "Completed") return meta.effectiveStatus === "Completed";
      return true;
    });
  }, [selectedRows, statusFocus, getTrackingMeta]);

  if (!hospital) return null;

  function handleEquipmentMultiSelect(event) {
    const values = Array.from(event.target.selectedOptions).map((option) => option.value);
    if (values.includes("all")) {
      setSelectedEquipmentIds([]);
      return;
    }
    setSelectedEquipmentIds(values);
  }

  function handleToggleSelectAll() {
    if (allSelected) {
      setSelectedEquipmentIds([]);
      return;
    }
    setSelectedEquipmentIds(rows.map((row) => String(row.id)));
  }

  async function copyEmailDraft() {
    if (!generatedEmailText) return;

    try {
      await navigator.clipboard.writeText(generatedEmailText);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch (error) {
      console.error("Failed to copy email draft", error);
    }
  }

  async function copyAiPrompt() {
    if (!emailDraft) return;

    try {
      await navigator.clipboard.writeText(buildAiPrompt(emailDraft, hospital));
      setCopiedAiPrompt(true);
      setTimeout(() => setCopiedAiPrompt(false), 1800);
    } catch (error) {
      console.error("Failed to copy AI prompt", error);
    }
  }

  async function copyEngineerMessage() {
    if (!engineerDispatchMessage.trim()) return;

    try {
      await navigator.clipboard.writeText(engineerDispatchMessage);
      setCopiedEngineerMessage(true);
      setTimeout(() => setCopiedEngineerMessage(false), 1800);
    } catch (error) {
      console.error("Failed to copy engineer dispatch message", error);
    }
  }

  function handleOpenEmailClient() {
    if (!canEmailSelected) return;
    onSendHospitalEmail?.(pendingRows, emailDraft.subject);
  }

  function handleNotifyEngineers() {
    if (!pendingRows.length) return;
    onSendHospitalEmail?.(pendingRows, "Engineer dispatch sent");
  }

  function handleAddComment(event) {
    event.preventDefault();
    if (!commentText.trim()) return;
    onAddHospitalComment?.({
      rowIds: selectedRows.map((row) => row.id),
      note: commentText.trim(),
      by: commentBy.trim() || "PM Coordinator",
    });
    setCommentText("");
  }

  return (
    <div className="card">
      <div className="detail-head">
        <div>
          <h2 className="section-title">Hospital Equipment Status</h2>
          <div className="hospital-headline">
            <Building2 size={16} className="inline-icon" />
            {hospital}
          </div>
        </div>
      </div>

      <div className="hospital-quick-actions compact-quick-actions">
        <div>
          <label className="muted">Select equipment (multi-select supported)</label>
          <select className="select equipment-multiselect" multiple value={selectedEquipmentIds} onChange={handleEquipmentMultiSelect}>
            <option value="all">All equipment ({rows.length})</option>
            {rows.map((row) => (
              <option key={row.id} value={String(row.id)}>
                {row.equipment} {row.serial ? `(${row.serial})` : ""}
              </option>
            ))}
          </select>
          <div className="selection-meta">{selectionLabel}</div>
          <button className="button button-soft" onClick={handleToggleSelectAll}>
            {allSelected ? <Square size={15} className="inline-icon" /> : <CheckSquare size={15} className="inline-icon" />}
            {allSelected ? "Clear manual selection" : "Select all equipment"}
          </button>
        </div>

        <div className="selection-meta">
          {selectedRows.length} selected · {pendingRows.length} pending
        </div>

        <div className="selection-buttons">
          <button className="button" onClick={copyEngineerMessage} disabled={!pendingRows.length}>
            <Wrench size={15} className="inline-icon" />
            {copiedEngineerMessage ? "Engineer list copied" : "Copy engineer list"}
          </button>
          <button className="button" onClick={handleNotifyEngineers} disabled={!pendingRows.length}>
            Notify engineers
          </button>
          {canEmailSelected ? (
            <a className="button button-primary" href={selectedMailTo} onClick={handleOpenEmailClient}>
              <Mail size={15} className="inline-icon" />
              Open email client
            </a>
          ) : (
            <button className="button" disabled title="No pending equipment to include.">
              <Mail size={15} className="inline-icon" />
              Open email client
            </button>
          )}
        </div>
      </div>

      <div className="hospital-insight-grid">
        <div className="hospital-kpi-card">
          <div className="muted">Overdue equipment</div>
          <div className="hospital-kpi-value">{statusSummary.overdue}</div>
        </div>
        <div className="hospital-kpi-card">
          <div className="muted">Due within 14 days</div>
          <div className="hospital-kpi-value">{statusSummary.dueSoon14}</div>
        </div>
        <div className="hospital-kpi-card">
          <div className="muted">Completed PM items</div>
          <div className="hospital-kpi-value">{statusSummary.completed}</div>
        </div>
        <div className="hospital-kpi-card">
          <div className="muted">Avg. response time</div>
          <div className="hospital-kpi-value">
            {averageResponseHours === null ? "N/A" : `${averageResponseHours}h`}
          </div>
        </div>
      </div>

      <div className="email-draft-wrap">
        <div className="email-draft-head">
          <div className="selection-meta">Email reminder draft ({pendingRows.length} pending item{pendingRows.length === 1 ? "" : "s"})</div>
          <div className="selection-buttons">
            <label className="muted ai-toggle-wrap">
              <input type="checkbox" checked={useAiTone} onChange={(event) => setUseAiTone(event.target.checked)} /> AI-friendly tone
            </label>
            <button className="button" onClick={copyAiPrompt} disabled={!generatedEmailText}>
              <Bot size={15} className="inline-icon" />
              {copiedAiPrompt ? "AI prompt copied" : "Copy AI prompt"}
            </button>
            <button className="button" onClick={copyEmailDraft} disabled={!generatedEmailText}>
              <Copy size={15} className="inline-icon" />
              {copied ? "Copied" : "Copy email text"}
            </button>
          </div>
        </div>
        <textarea
          className="input textarea email-draft-textarea"
          readOnly
          value={
            generatedEmailText ||
            "Select equipment (or All) to generate an email reminder draft for pending preventive maintenance items."
          }
        />
      </div>
      {quickActionFeedback ? <div className="quick-action-feedback">{quickActionFeedback}</div> : null}

      <div className="hospital-detail-layout">
        <div className="hospital-history-pane">
          <form className="comment-form" onSubmit={handleAddComment}>
            <div className="comment-form-head">
              <div className="selection-meta">
                <MessageSquare size={14} className="inline-icon" />
                Notes for {selectedEquipment ? selectedEquipment.equipment : "all selected equipment"}
              </div>
              <input className="input" value={commentBy} onChange={(event) => setCommentBy(event.target.value)} placeholder="Added by" />
            </div>
            <textarea
              className="input textarea"
              value={commentText}
              onChange={(event) => setCommentText(event.target.value)}
              placeholder="Add a follow-up note. It will be saved in the selected equipment communication history."
            />
            <button className="button" type="submit">Add note to history</button>
          </form>

          <div className="com-history-wrap com-history-major">
            <h3 className="section-title hospital-subsection-title">Dedicated Equipment + Contract History</h3>
            {communicationTimeline.length ? (
              <div className="history-list">
                {communicationTimeline.slice(0, 40).map((entry, idx) => (
                  <div key={`${entry.type}-${entry.at || entry.date}-${idx}`} className="history-item">
                    <div className="strong">{entry.type.toUpperCase()} · {entry.equipment || "General"}</div>
                    <div className="muted">{entry.serial || "No serial"} · {entry.by || entry.updatedBy || "System"} · {entry.at || entry.date || "Unknown date"}</div>
                    <div>{entry.note || entry.notes || entry.subject || "No details"}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="muted">No communication history yet for this selection.</div>
            )}
          </div>
        </div>
      </div>

      <div className="hospital-status-view">
        <div className="hospital-status-head">
          <h3 className="section-title hospital-subsection-title">Equipment Status View</h3>
          <div className="selection-buttons">
            <button className="button button-soft" onClick={() => setIsStatusViewOpen((value) => !value)}>
              {isStatusViewOpen ? "Hide status table" : "Show status table"}
            </button>
          </div>
        </div>
        {isStatusViewOpen ? (
          <>
            <div className="status-filter-row">
              {["All", "Overdue", "DueSoon", "Completed"].map((filterKey) => (
                <button
                  key={filterKey}
                  className={`button button-soft${statusFocus === filterKey ? " status-filter-active" : ""}`}
                  onClick={() => setStatusFocus(filterKey)}
                >
                  {filterKey === "DueSoon" ? "Due Soon" : filterKey}
                </button>
              ))}
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Equipment</th>
                    <th>Department</th>
                    <th>PM Required</th>
                    <th>PM Done</th>
                    <th>PM1</th>
                    <th>PM2</th>
                    <th>PM3</th>
                    <th>Other PM</th>
                    <th>Next PM</th>
                    <th>Timing</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {displayedRows.length ? (
                    displayedRows.map((row) => {
                      const meta = getTrackingMeta(row);
                      const requiredPmCount = Number(row.pmsPerYear) || 1;
                      const completedPmCount = (row.pmHistory || []).filter((entry) => entry.status === "Completed").length;
                      const pm1Status = completedPmCount >= 1 ? "Available" : "Required";
                      const pm2Status = completedPmCount >= 2 ? "Available" : "Required";
                      const pm3Status = completedPmCount >= 3 ? "Available" : "Required";
                      const otherPmStatus = requiredPmCount > 3 ? `${Math.max(0, completedPmCount - 3)}/${requiredPmCount - 3} available` : "N/A";
                      return (
                        <tr key={row.id} className={selectedEquipmentIds.length ? "hospital-status-row-selected" : ""}>
                          <td>
                            <div className="strong">{row.equipment}</div>
                            <div className="muted">{row.serial || "No serial"}</div>
                          </td>
                          <td>{row.department || "—"}</td>
                          <td>{requiredPmCount}</td>
                          <td>{completedPmCount}</td>
                          <td>{pm1Status}</td>
                          <td>{pm2Status}</td>
                          <td>{pm3Status}</td>
                          <td>{otherPmStatus}</td>
                          <td>{row.nextPmDate || "—"}</td>
                          <td className="muted">
                            {meta.isOverdue
                              ? "Overdue"
                              : meta.dueSoon7
                                ? "Due within 7 days"
                                : meta.dueSoon14
                                  ? "Due within 14 days"
                                  : "On schedule"}
                          </td>
                          <td>{meta.effectiveStatus}</td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan={11} className="muted">
                        No equipment found for this status filter.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <div className="muted">Status table is hidden to keep this view focused. Use "Show status table" when needed.</div>
        )}
      </div>
    </div>
  );
}
