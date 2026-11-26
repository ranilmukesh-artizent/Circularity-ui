import { Icon } from '../../components/Icon';
import type { PreviewModel } from '../../pages/modeler/proposal';
import './flow/flow.css';

/**
 * The intent preview card of plan 10 (2.3, rules R2 and R3): shown before any write the assistant can start. It states
 * the change, where it was read, what changes, the checks, the impact and the limits, then the person's choices.
 * One primary button at most (the only yellow element). T2 owns it; the dock (next steps) and the waiting strip (held
 * proposals) import it. Plain props, so a caller needs no proposal: sections of lines are enough.
 */
export interface CardLine {
  text: string;
  /** a revision mark of a diff line */
  sign?: '+' | '~' | '-';
  /** a check line: drawn with the `check` or `alert` icon */
  level?: 'ok' | 'warn';
}
export interface CardSection {
  heading: string;
  lines: CardLine[];
}
export interface CardAction {
  label: string;
  onClick(): void;
  primary?: boolean;
  disabled?: boolean;
}
export interface PreviewCardProps {
  title: string;
  /** the rule id at the title's right edge */
  tag?: string | null;
  /** "Read by the rules" and so on (2.5) */
  basis?: string;
  /** where else to see it, e.g. "Drawn dashed on the canvas" */
  where?: string;
  variant?: 'proposal' | 'held' | 'blocked';
  sections: CardSection[];
  limits?: string;
  actions: CardAction[];
  /** a line in place of the buttons the person may not use */
  note?: string;
  busy?: boolean;
}

const SIGN_LABEL = { '+': 'Added', '~': 'Changed', '-': 'Removed' } as const;

export function PreviewCard({ title, tag, basis, where, variant = 'proposal', sections, limits, actions, note, busy }: PreviewCardProps) {
  return (
    <div className={'as-card as-card-flow' + (variant === 'proposal' ? '' : ' ' + variant)} role="group" aria-label={title} aria-busy={busy || undefined}>
      <div className="as-card-head">
        <b className="as-card-title">{title}</b>
        {tag && <span className="as-card-tag">{tag}</span>}
      </div>
      {(basis || where) && (
        <div className="as-card-basis">
          {basis && <span>{basis}</span>}
          {where && <span>{where}</span>}
        </div>
      )}
      {sections.filter((s) => s.lines.length).map((s) => (
        <div key={s.heading} className="as-card-sec">
          <h4>{s.heading}</h4>
          <ul>
            {s.lines.map((l, i) => (
              <li key={i} className={l.level ?? undefined}>
                {l.sign && <span className="as-sign" role="img" aria-label={SIGN_LABEL[l.sign]}>{l.sign}</span>}
                {l.level && <Icon name={l.level === 'ok' ? 'check' : 'alert'} className="as-ic" />}
                <span>{l.text}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
      {limits && (
        <div className="as-card-sec">
          <h4>Limits</h4>
          <p>{limits}</p>
        </div>
      )}
      {note && <p className="as-card-note">{note}</p>}
      {actions.length > 0 && (
        <div className="as-card-actions">
          {actions.map((a) => (
            <button key={a.label} type="button" className={'btn sm' + (a.primary ? ' pri' : '')} disabled={a.disabled || busy} onClick={a.onClick}>{a.label}</button>
          ))}
        </div>
      )}
    </div>
  );
}

/** The sections of a card for a proposal's model (previewOf): what changes, the checks, the impact. */
export function sectionsOf(m: PreviewModel): CardSection[] {
  return [
    { heading: 'What changes', lines: m.diff.map((d) => ({ text: d.text, sign: d.sign })) },
    { heading: m.blocked ? 'Why' : 'Checks', lines: m.checks.map((c) => ({ text: c.text, level: c.level })) },
    ...(m.impact ? [{ heading: m.impact.heading, lines: m.impact.lines.map((text) => ({ text })) }] : []),
  ];
}
