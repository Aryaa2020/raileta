import React, { useEffect, useRef, useState } from 'react';
import { ArrowRight, Search, X } from 'lucide-react';
import KiroButton from '../../../shared/KiroButton';
import { matchingTrains, routeLabel } from '../../../shared/trainSearch.mjs';

export default function TrainSearch({ trains = [], onSearch, loading, rosterLoading }) {
  const [trainNumber, setTrainNumber] = useState('');
  const [showResults, setShowResults] = useState(false);
  const matches = matchingTrains(trains, trainNumber);
  const choose = train => { setTrainNumber(String(train.train_number)); setShowResults(false); onSearch(train.train_number); };
  const input = useRef(null);
  useEffect(() => {
    const focus = () => { input.current?.focus({ preventScroll: true }); input.current?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'center' }); };
    const shortcut = event => {
      if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey || event.target.closest('input,textarea,select,[contenteditable="true"]')) return;
      event.preventDefault(); focus();
    };
    window.addEventListener('keydown', shortcut);
    window.addEventListener('raileta:focus-search', focus);
    return () => { window.removeEventListener('keydown', shortcut); window.removeEventListener('raileta:focus-search', focus); };
  }, []);
  const submit = event => { event.preventDefault(); if (matches.length === 1) choose(matches[0]); else setShowResults(true); };
  return <section className="search-panel"><form onSubmit={submit}>
    <div className="train-input"><Search aria-hidden="true" /><input ref={input} value={trainNumber} onChange={event => { setTrainNumber(event.target.value); setShowResults(true); }} onKeyDown={event => { if (event.key === 'Escape') setShowResults(false); }} placeholder="Name, number, station or route" aria-label="Search trains" aria-describedby="train-search-help" autoComplete="off" />{trainNumber && <button className="clear-search" type="button" aria-label="Clear search" onClick={() => { setTrainNumber(''); setShowResults(false); input.current?.focus(); }}><X /></button>}</div>
    <KiroButton type="submit" className="primary-button" disabled={loading || rosterLoading || !trainNumber.trim()}><span>{loading ? 'Opening train…' : 'Find trains'}</span><ArrowRight /></KiroButton>
  </form><p className="search-hint" id="train-search-help">Try “Shatabdi”, “12027”, “Katpadi” or “Chennai to Bangalore”.<span><kbd>/</kbd> to search</span></p>
  {showResults && trainNumber.trim() && <section className="train-search-results" aria-label="Matching trains"><p role="status">{rosterLoading ? 'Loading available trains…' : matches.length ? `${matches.length} ${matches.length === 1 ? 'train matches' : 'trains match'} · choose a train` : 'No matching trains in this demo. Try a name, station code or Chennai to Bengaluru.'}</p>{matches.map(train => <button key={train.train_number} type="button" disabled={loading} onClick={() => choose(train)}><span><strong>{train.train_name}</strong><small>{train.train_number} · {routeLabel(train)}</small></span><ArrowRight aria-hidden="true" /></button>)}</section>}
  </section>;
}
