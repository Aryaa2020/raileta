import React from 'react';

export default function DisplayRow({ departure, isHeader = false }) {
  if (isHeader) return <div className="departure-row is-heading">{['TRAIN', 'SERVICE', 'DESTINATION', 'DEPARTURE', 'PLATFORM', 'STATUS'].map(label => <div key={label}>{label}</div>)}</div>;
  const { train_number, train_name, destination, scheduled_departure, predicted_departure, delay_minutes, platform, status } = departure;
  const statusValue = status?.toLowerCase();
  let statusColor = 'status-ontime';
  let statusText = status ? status.toUpperCase() : 'SCHEDULED';
  if (statusValue === 'cancelled') statusColor = 'status-cancelled';
  else if (statusValue !== 'departed' && Number.isFinite(delay_minutes) && delay_minutes > 10) {
    statusColor = delay_minutes > 30 ? 'status-late' : 'status-delayed';
    statusText = `LATE ${Math.round(delay_minutes)}M`;
  }
  return <div className="departure-row"><div className="departure-number">{train_number}</div><div className="departure-name">{train_name}</div><div className="departure-destination">{destination}</div><div className="departure-time">{predicted_departure || scheduled_departure || '—'}{delay_minutes > 5 && <small>{scheduled_departure}</small>}</div><div className="departure-platform">{platform || '—'}</div><div className={`departure-status ${statusColor}`}>{statusText}</div></div>;
}
