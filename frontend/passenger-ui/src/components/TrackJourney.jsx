import React from 'react';
import RevealText from '../../../shared/RevealText';

// A designed railway switch, not a map of train positions. Sleepers follow the
// tangent of the curve so both rails and ties stay aligned through the bend.
function trackGeometry() {
  const points = [], ties = [];
  let distance = 0;
  for (let i = 0; i <= 240; i++) {
    const t = i / 240, x = 25 + t * 1150;
    const y = 95 + Math.sin(t * Math.PI * 2) * 32;
    const slope = Math.cos(t * Math.PI * 2) * 32 * Math.PI * 2 / 1150;
    const norm = Math.sqrt(1 + slope * slope), nx = -slope / norm, ny = 1 / norm;
    if (i) distance += Math.hypot(x - points[i - 1].x, y - points[i - 1].y);
    if (distance > 17 || i === 0) { ties.push({ x1: x - nx * 17, y1: y - ny * 17, x2: x + nx * 17, y2: y + ny * 17 }); distance = 0; }
    points.push({ x, y, nx, ny });
  }
  return { ties, rails: [-7, 7].map(offset => points.map(({ x, y, nx, ny }, i) => `${i ? 'L' : 'M'}${x + nx * offset},${y + ny * offset}`).join(' ')) };
}
const geometry = trackGeometry();

export default function TrackJourney() {
  return <section className="track-journey" aria-labelledby="track-title">
    <div className="track-heading"><div><p className="eyebrow">Everything connects</p><RevealText id="track-title" text={'Different questions.\nOne clear line.'} /></div><p>From finding your train to understanding its story.<br />Pick a stop. Take a closer look.</p></div>
    <nav className="journey-track" aria-label="Page journey navigation">
      <svg viewBox="0 0 1200 200" preserveAspectRatio="none" aria-hidden="true"><g className="track-sleepers">{geometry.ties.map((tie, index) => <line key={index} {...tie} />)}</g><g className="track-rails">{geometry.rails.map((d, index) => <path key={index} d={d} />)}</g><path className="track-switch" d="M650 87 C805 62 880 159 1010 171 L1175 171 M650 102 C805 77 880 173 1010 185 L1175 185" /><path className="track-signal" d={geometry.rails[0]} /></svg>
      {[{ id: 'train-search', name: 'Find your train', label: '01 / EXPLORE' }, { id: 'how-it-works', name: 'Read the prediction', label: '02 / UNDERSTAND' }, { id: 'data-notes', name: 'Know the source', label: '03 / INSPECT' }].map((stop, i) => {
        const t = .15 + i * .35;
        const left = (25 + t * 1150) / 1200 * 100;
        const top = (95 + Math.sin(t * Math.PI * 2) * 32) * .9;
        return <a className="journey-stop" style={{ '--stop-left': `${left}%`, '--stop-top': `${top}px` }} key={stop.id} href={`#${stop.id}`}><span className="journey-stop-dot" /><span className="journey-stop-label">{stop.label}</span><strong>{stop.name}<span aria-hidden="true"> ↗</span></strong></a>;
      })}
    </nav>
    <p className="track-signoff"><span>RAILETA — MADE FOR THE JOURNEY</span><span>Follow the line. Find the context.</span></p>
  </section>;
}
