/**
 * The modes of the one assistant, in the order of the mode radio. T2 (Change flow) and T3 (Set up) each add one line:
 * import their mode and list it here.
 */
import type { ModeDef } from '../types';
import { askMode } from './ask';

export const MODES: ModeDef[] = [askMode];
