/** Worked pack questions (plan 9, P9-6.17, DV-13): small pure helpers for the view. The list of questions per pack comes from the server (`worked_questions` of the pack view). */
import type { PackAnswer, QuestionPoint } from '../../api/analytics';

/** The title of an answer: the question text the server sent, else its id. */
export const answerTitle = (a: Pick<PackAnswer, 'question_id' | 'question'>): string => a.question || a.question_id;

/** The share of the total that the top `n` points of a bar series make, as "58%" (the same rounding the server uses). */
export function topShare(series: { x: string; y: number | null }[], n = 2): string {
  const ys = series.map((p) => p.y ?? 0).sort((a, b) => b - a);
  const total = ys.reduce((s, y) => s + y, 0);
  return total ? Math.round((ys.slice(0, n).reduce((s, y) => s + y, 0) / total) * 100) + '%' : '0%';
}

/** The points of a line that have a value, with their x position (0..1) and y position (0..1, 1 on top) for an SVG. */
export function plot(points: QuestionPoint[], lo: number, hi: number): { x: number; y: number; p: QuestionPoint }[] {
  const span = hi - lo || 1;
  return points.flatMap((p, i) => (p.y === null ? [] : [{ x: points.length > 1 ? i / (points.length - 1) : 0.5, y: (p.y - lo) / span, p }]));
}
