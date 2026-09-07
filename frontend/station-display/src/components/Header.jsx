/**
 * Display header with station info and clock
 */
import React, { useState, useEffect } from 'react';


const Header = ({ stationName, stationCode, historical = false }) => {
  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  return (
    <div className="shrink-0 bg-gradient-to-r from-red-900 via-red-800 to-red-900 border-b-8 border-yellow-500 px-8 py-6">
      <div className="flex justify-between items-center gap-6">
        {/* Station Info */}
        <div>
          <h1 className="text-3xl lg:text-3xl font-black led-text text-yellow-300 mb-2">
            {historical ? 'HISTORICAL DELAY PROFILES' : stationName || 'RAILWAY STATION'}
          </h1>
          <p className="text-lg led-text text-yellow-400">
            {historical ? 'No departure records in the supplied dataset' : `Station Code: ${stationCode || 'XXX'}`}
          </p>
        </div>
        
        {/* Date and Time */}
        <div className="text-right">
          {historical && <p className="mb-1 text-xs text-yellow-400">PRESENT CLOCK · IST</p>}
          <div className="text-3xl lg:text-3xl font-black led-text text-green-400 mb-2">
            {currentTime.toLocaleTimeString('en-GB', { timeZone: 'Asia/Kolkata' })}
          </div>
          <div className="text-lg led-text text-yellow-400">
            {currentTime.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'Asia/Kolkata' })}
          </div>
        </div>
      </div>
      
      {/* Departures Title */}
      <div className="mt-6 text-center">
        <h2 className="text-3xl font-black led-text text-yellow-300">
          {historical ? '⟵ AGGREGATE PROFILE REPLAY ⟶' : '⟵ DEPARTURES ⟶'}
        </h2>
      </div>
    </div>
  );
};

export default Header;
