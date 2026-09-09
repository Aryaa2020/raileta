import React, { useEffect, useRef, useState } from 'react';

// One accessible label; the individual letters are purely visual. Reveal once
// per heading, so refreshing train data never replays the introduction.
export default function RevealText({ as: Tag = 'h2', text, className = '', ...props }) {
  const element = useRef(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!window.IntersectionObserver || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) { setVisible(true); observer.disconnect(); }
    }, { threshold: 0.15 });
    if (element.current) observer.observe(element.current);
    return () => observer.disconnect();
  }, []);
  let index = 0;
  return <Tag {...props} ref={element} aria-label={text.replaceAll('\n', ' ')} className={`reveal-text ${visible ? 'is-visible' : ''} ${className}`}>
    {text.split('\n').map((line, lineIndex) => <span className="reveal-line" aria-hidden="true" key={lineIndex}>
      {line.split(/(\s+)/).map((word, wordIndex) => /^\s+$/.test(word) ? ' ' : <span className="reveal-word" key={wordIndex}>{[...word].map(letter => <span className="reveal-char" key={index} style={{ '--letter-delay': `${index++ * 22}ms` }}>{letter}</span>)}</span>)}
    </span>)}
  </Tag>;
}
