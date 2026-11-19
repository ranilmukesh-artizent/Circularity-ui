/** The demo's formatters, so every page prints numbers and dates exactly as index.html does. */
import { engine } from '../engine/engine';

type F<A extends unknown[] = [unknown]> = (...a: A) => string;
const f = <A extends unknown[] = [unknown]>(name: string): F<A> => (...a: A) => engine()<F<A>>(name)(...a);

/** $1,234 / −$1,234 */
export const money = f<[number]>('money');
/** 07 Oct */
export const fmtDate = f<[Date | string | number]>('fmtD');
/** 07 Oct 2026 */
export const fmtDateYear = f<[Date | string | number]>('fmtDY');
/** 1,234 */
export const fmtNumber = f<[number]>('fmtN');
