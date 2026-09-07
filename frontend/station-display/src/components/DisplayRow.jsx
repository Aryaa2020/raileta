/**
 * Single departure row in LED display style
 */
import React from 'react';

const DisplayRow = ({ departure, isHeader = false }) => {
  if (isHeader) {
    return (
      <div className="min-w-0 grid grid-cols-12 gap-4 px-8 py-4 border-b-4 border-yellow-600 bg-black text-yellow-400">
        <div className="col-span-2 text-sm lg:text-lg font-bold">TRAIN</div>
        <div className="col-span-3 text-sm lg:text-lg font-bold">NAME</div>
        <div className="col-span-2 text-sm lg:text-lg font-bold">DEST</div>
        <div className="col-span-2 text-sm lg:text-lg font-bold">TIME</div>
        <div className="col-span-1 text-sm lg:text-lg font-bold">PLT</div>
        <div className="col-span-2 text-sm lg:text-lg font-bold">STATUS</div>
      </div>
    );
  }

  const { 
    train_number, 
    train_name, 
    destination, 
    scheduled_departure,
    predicted_departure,
    delay_minutes, 
    platform, 
    status 
  } = departure;

  // Determine status color
  let statusColor = 'status-ontime';
  let statusText = status ? status.toUpperCase() : 'SCHEDULED';

  if (status && status.toLowerCase() === 'departed') {
    statusColor = 'status-ontime';
    statusText = 'DEPARTED';
  } else if (delay_minutes == null) {
    statusColor = 'status-ontime';
  } else if (delay_minutes > 30) {
    statusColor = 'status-late blink';
    statusText = `LATE ${Math.round(delay_minutes)}M`;
  } else if (delay_minutes > 10) {
    statusColor = 'status-delayed';
    statusText = `LATE ${Math.round(delay_minutes)}M`;
  }

  return (
    <div className="min-w-0 grid grid-cols-12 gap-4 px-8 py-6 border-b-2 border-yellow-900 hover:bg-yellow-900 hover:bg-opacity-10 transition-colors">
      {/* Train Number */}
      <div className="col-span-2 text-xl lg:text-3xl font-bold led-text text-yellow-400">
        {train_number}
      </div>
      
      {/* Train Name */}
      <div className="col-span-3 text-base lg:text-xl font-medium led-text text-yellow-300 truncate">
        {train_name}
      </div>
      
      {/* Destination */}
      <div className="col-span-2 text-base lg:text-xl font-bold led-text text-yellow-400">
        {destination}
      </div>
      
      {/* Time */}
      <div className="col-span-2 flex flex-col">
        <div className={`text-2xl lg:text-4xl font-black led-text ${
          delay_minutes > 10 ? 'text-orange-400' : 'text-green-400'
        }`}>
          {predicted_departure || scheduled_departure || '—'}
        </div>
        {delay_minutes > 5 && (
          <div className="text-xl text-gray-500 line-through mt-1">
            {scheduled_departure}
          </div>
        )}
      </div>
      
      {/* Platform */}
      <div className="col-span-1 text-2xl lg:text-4xl font-black led-text text-cyan-400">
        {platform || '-'}
      </div>
      
      {/* Status */}
      <div className={`col-span-2 text-base lg:text-xl break-words font-black led-text ${statusColor}`}>
        {statusText}
      </div>
    </div>
  );
};

export default DisplayRow;
