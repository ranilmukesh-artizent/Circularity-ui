import type { KeyboardEvent } from 'react';

/**
 * Keyboard twin of a click handler for a clickable row or tile that is not a button (tabIndex={0}): Enter and Space
 * run `fn`, as they do on a button. Keys pressed on a control inside the row (its own buttons and links) are left to
 * that control.
 */
export const onActivateKey = (fn: () => void) => (e: KeyboardEvent) => {
  if (e.target !== e.currentTarget || (e.key !== 'Enter' && e.key !== ' ')) return;
  e.preventDefault();
  fn();
};
