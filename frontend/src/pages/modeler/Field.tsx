import type { ReactNode } from 'react';

/**
 * A form field of the Modeler's panels (plan 10 follow-up, QA A items 5, 10, 12): the label is always visible and sits
 * above the control, the hint (units, what happens if it is left empty) under it. `id` is the control's id.
 */
export function Field({ id, label, hint, wide, children }: { id: string; label: ReactNode; hint?: ReactNode; wide?: boolean; children: ReactNode }) {
  return (
    <div className={'mdl-field' + (wide ? ' wide' : '')}>
      <label htmlFor={id}>{label}</label>
      {children}
      {hint != null && <span className="hint" id={id + '-hint'}>{hint}</span>}
    </div>
  );
}

/** Why a button is off, in words: shown beside it, and as its title. Null when it is on. */
export function WhyOff({ id, why }: { id: string; why: string | null }) {
  return why ? <span className="note mdl-why" id={id}>{why}</span> : null;
}
