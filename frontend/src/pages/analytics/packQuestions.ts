/** The device pack's worked questions (plan 9, P9-6.17, DV-13): the ids `device.question` answers and small pure helpers for the view. */
import type { PackAnswer, QuestionPoint } from '../../api/analytics';

export const DEVICE_QUESTIONS: { id: string; question: string }[] = [
  { id: 'price_after_launch', question: 'Why did price realised drop?' },
  { id: 'disputes_by_partner', question: 'Who causes grading disputes?' },
];

/** The title of an answer: the question text the server sent, else the pack's own text for its id. */
export const answerTitle = (a: Pick<PackAnswer, 'question_id' | 'question'>): string =>
  a.question || DEVICE_QUESTIONS.find((q) => q.id === a.question_id)?.question || a.question_id;

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
