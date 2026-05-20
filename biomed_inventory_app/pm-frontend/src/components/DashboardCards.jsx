import React from "react";
import { AlertTriangle, Bell, CheckCircle2, ClipboardList } from "lucide-react";

export default function DashboardCards({ metrics, timingFilter, onMetricFilterSelect }) {
  function handleCardClick(nextTimingFilter) {
    if (onMetricFilterSelect) onMetricFilterSelect(nextTimingFilter);
  }

  const totalIsActive = timingFilter === "All";
  const dueThisWeekIsActive = timingFilter === "Due this week";
  const overdueIsActive = timingFilter === "Overdue only";
  const completedIsActive = timingFilter === "Completed";

  return (
    <div className="metrics-grid">
      <button
        type="button"
        className={`card metric-card-button ${totalIsActive ? "metric-card-active" : ""}`}
        onClick={() => handleCardClick("All")}
      >
        <div className="metric-row">
          <div>
            <div className="metric-label">Total Equipment</div>
            <div className="metric-value">{metrics.total}</div>
          </div>
          <ClipboardList />
        </div>
      </button>

      <button
        type="button"
        className={`card metric-card-button ${overdueIsActive ? "metric-card-active" : ""}`}
        onClick={() => handleCardClick("Overdue only")}
      >
        <div className="metric-row">
          <div>
            <div className="metric-label">Overdue</div>
            <div className="metric-value">{metrics.overdue}</div>
          </div>
          <AlertTriangle />
        </div>
      </button>

      <button
        type="button"
        className={`card metric-card-button ${dueThisWeekIsActive ? "metric-card-active" : ""}`}
        onClick={() => handleCardClick("Due this week")}
      >
        <div className="metric-row">
          <div>
            <div className="metric-label">Due This Week</div>
            <div className="metric-value">{metrics.dueThisWeek}</div>
          </div>
          <Bell />
        </div>
      </button>

      <button
        type="button"
        className={`card metric-card-button ${completedIsActive ? "metric-card-active" : ""}`}
        onClick={() => handleCardClick("Completed")}
      >
        <div className="metric-row">
          <div>
            <div className="metric-label">Completed</div>
            <div className="metric-value">{metrics.completed}</div>
          </div>
          <CheckCircle2 />
        </div>
      </button>
    </div>
  );
}
