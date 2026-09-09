import React from 'react';

export default function KiroButton({ href, variant = 'purple', className = '', children, ...props }) {
  const Tag = href ? 'a' : 'button';
  return <Tag {...(href ? { href } : { type: 'button' })} {...props} className={`kiro-button kiro-button--${variant} ${className}`}>
    <span className="kiro-button-content">{children}</span>
    <span className="kiro-button-fill" aria-hidden="true" />
  </Tag>;
}
