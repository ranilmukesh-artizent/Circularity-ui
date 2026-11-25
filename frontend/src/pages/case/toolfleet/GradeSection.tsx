import type { GradeView } from '../../../api/toolFleet';

/** "6 h ago", "2 d ago" or "just now" for the hours since grading. */
const ago = (h: number | null): string => (h == null || h < 1 ? 'just now' : h < 48 ? `${Math.round(h)} h ago` : `${Math.round(h / 24)} d ago`);

/** "Grade B · workbench DR-50412 · graded 6 h ago", or "Grade C · estimate (workbench grade not in yet)". */
export const gradeLine = (g: GradeView): string =>
  g.source === 'workbench'
    ? `Grade ${g.grade} · workbench${g.ref ? ' ' + g.ref : ''} · graded ${ago(g.age_hours)}`
    : `Grade ${g.grade} · estimate (workbench grade not in yet)`;

/** The grade of a tool and where it came from; an estimate carries an "Estimate" chip. */
export function GradeSection({ grade }: { grade: GradeView }) {
  return (
    <p style={{ margin: 0 }} data-testid="tf-grade">
      {gradeLine(grade)} {grade.source === 'estimate' && <span className="chip warn">Estimate</span>}
    </p>
  );
}