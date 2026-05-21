import React from "react";
import { AlertTriangle, Building2, Lightbulb } from "lucide-react";

export default function HospitalSummary({
  byHospital,
  selectedHospital,
  onSelectHospital,
  hospitalSummaryFilter,
  onHospitalSummaryFilterChange,
  quickActions,
}) {
  const visibleHospitals =
    hospitalSummaryFilter === "All"
      ? byHospital
      : byHospital.filter((item) => item.hospital === hospitalSummaryFilter);

  return (
    <div className="card hospital-summary-card">
      <div className="hospital-summary-head">
        <h2 className="section-title">Hospital Summary</h2>
        <select
          className="select hospital-summary-filter"
          value={hospitalSummaryFilter}
          onChange={(event) => onHospitalSummaryFilterChange(event.target.value)}
        >
          <option value="All">All hospitals</option>
          {byHospital.map((item) => (
            <option key={item.hospital} value={item.hospital}>
              {item.hospital}
            </option>
          ))}
        </select>
      </div>
      {quickActions ? <div className="hospital-summary-quick-actions">{quickActions}</div> : null}
      <div className="hospital-list">
        {visibleHospitals.map((item) => (
          <button
            key={item.hospital}
            className={`hospital-item hospital-button ${selectedHospital === item.hospital ? "hospital-item-active" : ""}`}
            onClick={() => onSelectHospital(item.hospital)}
          >
            <div className="hospital-head">
              <div>
                <div className="hospital-title">{item.hospital}</div>
                <div className="hospital-subtitle">{item.total} equipment items</div>
              </div>
              <Building2 size={18} />
            </div>

            <div className="hospital-stats">
              <div className="stat-box">
                <div className="stat-label">PM done / required</div>
                <div className="stat-value">
                  {item.pmCompletedTotal}/{item.pmRequiredTotal}
                </div>
              </div>
              <div className="stat-box">
                <div className="stat-label">PM placeholders filled</div>
                <div className="stat-value">{item.pmPlaceholdersFilled}</div>
              </div>
              <div className="stat-box">
                <div className="stat-label">PM available to do</div>
                <div className="stat-value">{item.pmAvailableToDo}</div>
              </div>
              <div className="stat-box">
                <div className="stat-label">Upcoming</div>
                <div className="stat-value">{item.upcoming}</div>
              </div>
              <div className="stat-box">
                <div className="stat-label">Due in 7d</div>
                <div className="stat-value">{item.dueSoon}</div>
              </div>
              <div className="stat-box">
                <div className="stat-label">Overdue</div>
                <div className="stat-value">{item.overdue}</div>
              </div>
            </div>
            {item.overdue || item.dueSoon ? (
              <div className="recommendation-row">
                {item.overdue ? <AlertTriangle size={14} /> : <Lightbulb size={14} />}
                {item.overdue
                  ? `${item.overdue} overdue item(s). Open detail and send staged follow-up.`
                  : `${item.dueSoon} due soon. Confirm hospital availability.`}
              </div>
            ) : null}
          </button>
        ))}
      </div>
    </div>
  );
}
