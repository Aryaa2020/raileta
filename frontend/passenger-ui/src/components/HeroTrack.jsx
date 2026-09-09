import React from 'react';

// Sample a centre line by distance so both rails stay parallel and sleepers
// remain evenly spaced through the bend. This is decoration, not live progress.
function makeTrack(curves, spacing = 18, gauge = 23) {
  const points = [];
  for (const [a, b, c, d] of curves) {
    for (let step = 0; step <= 160; step++) {
      const t = step / 160;
      const u = 1 - t;
      points.push({
        x: u ** 3 * a[0] + 3 * u * u * t * b[0] + 3 * u * t * t * c[0] + t ** 3 * d[0],
        y: u ** 3 * a[1] + 3 * u * u * t * b[1] + 3 * u * t * t * c[1] + t ** 3 * d[1],
      });
    }
  }
  const samples = [];
  let distance = 0;
  let next = 0;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1];
    const b = points[i];
    const length = Math.hypot(b.x - a.x, b.y - a.y);
    if (!length) continue;
    while (next <= distance + length) {
      const t = (next - distance) / length;
      samples.push({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t, nx: -(b.y - a.y) / length, ny: (b.x - a.x) / length });
      next += spacing;
    }
    distance += length;
  }
  const offset = (p, amount) => `${(p.x + p.nx * amount).toFixed(2)},${(p.y + p.ny * amount).toFixed(2)}`;
  return {
    rails: [-gauge / 2, gauge / 2].map(amount => samples.map((p, i) => `${i ? 'L' : 'M'}${offset(p, amount)}`).join(' ')),
    sleepers: samples.map(p => `M${offset(p, -gauge / 2 - 6)} L${offset(p, gauge / 2 + 6)}`),
  };
}

const sweepingTrack = makeTrack([
  [[-80, 526], [360, 506], [908, 674], [970, 340]],
  [[970, 340], [1016, 92], [1018, 42], [1520, 42]],
], 24, 48);
const compactTrack = makeTrack([
  [[-80, 134], [400, 134], [600, 48], [1200, 48]],
], 30, 44);

function TrackDrawing({ track, compact = false }) {
  return <svg className={`hero-track ${compact ? 'hero-track-compact' : 'hero-track-sweep'}`} viewBox={compact ? '0 0 1120 180' : '0 0 1440 600'} preserveAspectRatio="none" aria-hidden="true" focusable="false">
    <g className="hero-track-sleepers">
      {track.sleepers.map((d, i) => <path key={i} d={d} style={{ '--track-delay': `${180 + i * 1100 / (track.sleepers.length - 1)}ms` }} />)}
    </g>
    <g className="hero-track-rails">
      {track.rails.map((d, i) => <path key={i} d={d} pathLength="1" style={{ '--track-delay': `${180 + i * 80}ms` }} />)}
    </g>
  </svg>;
}

export default function HeroTrack() {
  return <><TrackDrawing track={sweepingTrack} /><TrackDrawing track={compactTrack} compact /></>;
}
