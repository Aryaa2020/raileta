import React from 'react';
const DelayChip = ({ reason }) => { const minutes = Number(reason.minutes || 0); return <div className="delay-chip"><span className="delay-icon">{reason.icon || '◌'}</span><div><p>{reason.description}</p><span>{minutes > 0 ? '+' : ''}{minutes.toFixed(1)} min contribution</span></div></div>; };
export default DelayChip;
