import React, { useState } from 'react';
import KiroButton from './KiroButton';

export function surfaceUrl(surface) {
  const ports = { passenger: '3000', controller: '3002', station: '3001' };
  const configured = { passenger: import.meta.env.VITE_PASSENGER_URL, controller: import.meta.env.VITE_CONTROLLER_URL, station: import.meta.env.VITE_STATION_URL };
  if (configured[surface]) return configured[surface];
  const url = new URL(window.location.href);
  url.port = ports[surface]; url.pathname = '/'; url.search = ''; url.hash = '';
  return url.href;
}

export function RailMark() {
  return <svg viewBox="0 0 32 36" fill="none" aria-hidden="true"><path d="M7 26 3 33m22-7 4 7M8 31h16" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"/><rect x="4" y="2" width="24" height="26" rx="8" fill="currentColor"/><path d="M10 8h12v8H10z" fill="var(--rail-ink, #17141d)"/><path d="M16 8v8" stroke="currentColor" strokeWidth="2"/><circle cx="10" cy="22" r="2" fill="var(--rail-ink, #17141d)"/><circle cx="22" cy="22" r="2" fill="var(--rail-ink, #17141d)"/></svg>;
}

export default function Navigation({ active = 'passenger', historical, onHome, onRefresh, refreshing, sourceLabel }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const links = [{ id: 'passenger', label: 'Train explorer' }, { id: 'controller', label: 'Operations' }, { id: 'station', label: 'Station board' }];
  return <><a className="skip-link" href="#main-content">Skip to content</a><header className="site-nav">
    <a className="rail-brand" href={surfaceUrl('passenger')} onClick={active === 'passenger' ? e => { e.preventDefault(); onHome?.(); setMenuOpen(false); } : undefined}><RailMark /><span>RAILETA</span></a>
    <button className="nav-menu-toggle" type="button" aria-label="Toggle navigation" aria-expanded={menuOpen} aria-controls="primary-nav" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? 'Close −' : 'Menu +'}</button>
    <nav id="primary-nav" aria-label="Main navigation" className={`nav-links ${menuOpen ? 'is-open' : ''}`}>
      {links.map(link => <a key={link.id} aria-current={active === link.id ? 'page' : undefined} href={link.id === active ? (active === 'passenger' ? '#train-search' : '#main-content') : surfaceUrl(link.id)} onClick={() => setMenuOpen(false)}>{link.label}</a>)}
      {active === 'passenger' && <a href="#how-it-works" onClick={() => setMenuOpen(false)}>How it works</a>}
    </nav>
    <div className="nav-actions"><span className="source-status"><i />{sourceLabel || (historical ? 'Historical replay' : historical === false ? 'Prototype feed' : 'Connecting')}</span>{onRefresh ? <KiroButton variant="white" className="nav-cta" title={active === 'controller' ? 'Refresh corridor and selected train' : 'Refresh station data'} aria-label={active === 'controller' ? 'Refresh corridor and selected train' : 'Refresh station data'} aria-busy={refreshing} disabled={refreshing} onClick={onRefresh}>{refreshing ? 'Refreshing…' : 'Refresh ↻'}</KiroButton> : <KiroButton variant="white" className="nav-cta" onClick={() => window.dispatchEvent(new Event('raileta:focus-search'))}>Find a train <span className="shortcut-key" aria-hidden="true">/</span></KiroButton>}</div>
  </header></>;
}
