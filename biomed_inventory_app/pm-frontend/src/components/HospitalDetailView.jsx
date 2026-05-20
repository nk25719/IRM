import React, { useMemo, useState } from 'react';
import { ArrowLeft, Mail, MessageSquare, Send } from 'lucide-react';

export default function HospitalDetailView({
  hospital,
  rows,
  getTrackingMeta,
  onSendHospitalEmail,
  onAddHospitalComment,
  quickActionFeedback,
}) {
  const [selectedIds, setSelectedIds] = useState([]);
  const [comment, setComment] = useState('');
  const [author, setAuthor] = useState('PM Coordinator');

  const selectedRows = useMemo(
    () => rows.filter((row) => selectedIds.includes(row.id)),
    [rows, selectedIds]
  );

  function toggleRow(id) {
    setSelectedIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id]
    );
  }

  function selectAll() {
    setSelectedIds(rows.map((row) => row.id));
  }

  function clearSelection() {
    setSelectedIds([]);
  }

  function addComment() {
    if (!comment.trim() || !selectedIds.length) return;
    onAddHospitalComment?.({ rowIds: selectedIds, note: comment.trim(), by: author || 'PM Coordinator' });
    setComment('');
  }

  return (
    <div className="card hospital-detail-card">
      <div className="detail-head">
        <div>
          <h2 className="section-title">Hospital PM Detail</h2>
          <div className="hospital-headline">{hospital || 'Unknown hospital'} · {rows.length} equipment item(s)</div>
        </div>
        <button className="button button-soft" onClick={() => window.location.reload()}>
          <ArrowLeft size={15} className="inline-icon" />
          Back
        </button>
      </div>

      {quickActionFeedback ? <div className="feedback-banner">{quickActionFeedback}</div> : null}

      <div className="actions actions-friendly">
        <button className="button button-soft" onClick={selectAll}>Select all</button>
        <button className="button button-soft" onClick={clearSelection}>Clear</button>
        <button className="button button-primary" onClick={() => onSendHospitalEmail?.(selectedRows, 'Hospital PM follow-up email')}>
          <Mail size={15} className="inline-icon" />
          Email selected
        </button>
        <button className="button button-soft" onClick={() => onSendHospitalEmail?.(rows, 'Hospital PM follow-up email')}>
          <Send size={15} className="inline-icon" />
          Email all pending
        </button>
      </div>

      <div className="card form-card">
        <div className="form-head">
          <h2 className="section-title">Add communication note</h2>
        </div>
        <div className="form-grid">
          <input className="input" value={author} onChange={(e) => setAuthor(e.target.value)} placeholder="Updated by" />
          <input className="input" value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Comment / call note" />
          <button className="button button-primary" onClick={addComment} disabled={!selectedIds.length || !comment.trim()}>
            <MessageSquare size={15} className="inline-icon" />
            Add to selected
          </button>
        </div>
      </div>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Select</th>
              <th>Equipment</th>
              <th>Model</th>
              <th>Serial</th>
              <th>Department</th>
              <th>Next PM</th>
              <th>Status</th>
              <th>Engineer</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const meta = getTrackingMeta(row);
              return (
                <tr key={row.id}>
                  <td><input type="checkbox" checked={selectedIds.includes(row.id)} onChange={() => toggleRow(row.id)} /></td>
                  <td className="strong">{row.equipment || '—'}</td>
                  <td>{row.model || '—'}</td>
                  <td>{row.serial || '—'}</td>
                  <td>{row.department || '—'}</td>
                  <td>{row.nextPmDate || '—'}</td>
                  <td><span className={meta.isOverdue ? 'badge badge-overdue' : meta.dueSoon7 ? 'badge badge-due-soon' : 'badge badge-default'}>{meta.effectiveStatus}</span></td>
                  <td>{row.engineer || '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
