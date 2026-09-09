import React, { useEffect, useRef, useState } from 'react';
import { ArrowRight, Search, X } from 'lucide-react';
import KiroButton from '../../../shared/KiroButton';

export default function TrainSearch({ onSearch, loading, historical }) {
  const [trainNumber, setTrainNumber] = useState('');
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
  const submit = event => { event.preventDefault(); if (trainNumber.trim()) onSearch(trainNumber.trim()); };
  return <section className="search-panel"><form onSubmit={submit}>
    <div className="train-input"><Search aria-hidden="true" /><input ref={input} value={trainNumber} onChange={event => setTrainNumber(event.target.value)} placeholder="Enter a train number" inputMode="numeric" aria-label="Train number" autoComplete="off" />{trainNumber && <button className="clear-search" type="button" aria-label="Clear train number" onClick={() => { setTrainNumber(''); input.current?.focus(); }}><X /></button>}</div>
    <KiroButton type="submit" className="primary-button" disabled={loading || !trainNumber.trim()}><span>{loading ? 'Finding train…' : historical ? 'Explore train' : 'Track train'}</span><ArrowRight /></KiroButton>
  </form><p className="search-hint">Search by number, or choose a train below.<span><kbd>/</kbd> to search</span></p></section>;
}
