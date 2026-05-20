import React from "react";
import { Search } from "lucide-react";

const timingOptions = ["All", "Overdue only", "Due this week", "Due this month", "Completed"];
const sortOptions = ["None", "Hospital", "Next PM date", "Overdue", "Engineer"];

export default function FiltersBar({
  search,
  setSearch,
  hospitalFilter,
  setHospitalFilter,
  statusFilter,
  setStatusFilter,
  timingFilter,
  setTimingFilter,
  sortBy,
  setSortBy,
  hospitals,
  statuses,
}) {
  return (
    <div className="card filters-card">
      <div className="filters-grid">
        <div className="search-wrap">
          <Search size={16} className="search-icon" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search hospital, equipment, model, serial, engineer..."
            className="input search-input"
          />
        </div>

        <select value={hospitalFilter} onChange={(e) => setHospitalFilter(e.target.value)} className="select">
          {hospitals.map((hospital) => (
            <option key={hospital} value={hospital}>
              {hospital}
            </option>
          ))}
        </select>

        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="select">
          {statuses.map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </select>

        <select value={timingFilter} onChange={(e) => setTimingFilter(e.target.value)} className="select">
          {timingOptions.map((filterOption) => (
            <option key={filterOption} value={filterOption}>
              {filterOption}
            </option>
          ))}
        </select>

        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className="select">
          {sortOptions.map((option) => (
            <option key={option} value={option}>
              Sort: {option}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
