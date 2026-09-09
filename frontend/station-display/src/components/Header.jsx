import React, { useState, useEffect } from 'react';

import RevealText from '../../../shared/RevealText';

export default function Header({ stationName, stationCode, historical }) {
  const [currentTime, setCurrentTime] = useState(new Date());
  useEffect(() => { const timer = setInterval(() => setCurrentTime(new Date()), 1000); return () => clearInterval(timer); }, []);
  return <header className="station-heading"><div><p className="eyebrow">{historical ? 'HISTORICAL DELAY PROFILES' : `STATION ${stationCode} / DEPARTURES`}</p><RevealText key={historical ? 'historical' : stationName} as="h1" text={historical ? 'Every station.\nA new perspective.' : stationName} /><p>{historical ? 'Explore what the dataset tells us, and where its story ends.' : 'Reported departures, platform information, and station updates.'}</p></div><div className="station-clock"><p>PRESENT CLOCK · IST</p><time dateTime={currentTime.toISOString()}>{currentTime.toLocaleTimeString('en-GB', { timeZone: 'Asia/Kolkata' })}</time><span>{currentTime.toLocaleDateString('en-GB', { day: '2-digit', month: 'long', year: 'numeric', timeZone: 'Asia/Kolkata' })}</span></div></header>;
}
