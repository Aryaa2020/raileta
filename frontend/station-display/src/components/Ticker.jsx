import React from 'react';

export default function Ticker({ message }) {
  return <aside className="station-notice"><span>DATA NOTE</span><p>{message}</p></aside>;
}
