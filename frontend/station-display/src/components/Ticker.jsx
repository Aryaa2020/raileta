/**
 * Scrolling ticker at bottom of display
 */
import React from 'react';

const Ticker = ({ message }) => {
  const defaultMessage = "RailETA - Event-Driven Train Predictions • Mock Windows · 80% Coverage Target • Plain-Language Delay Reasons";
  
  return (
    <div className="shrink-0 order-last bg-red-900 border-t-4 border-yellow-500 overflow-hidden">
      <div className="py-4">
        <div className="ticker whitespace-nowrap text-lg font-bold led-text text-yellow-300">
          {message || defaultMessage}
        </div>
      </div>
    </div>
  );
};

export default Ticker;
