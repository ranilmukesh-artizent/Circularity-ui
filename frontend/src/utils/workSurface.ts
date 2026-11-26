/**
 * Plan 10 section 5: how a page tells the assistant dock what it is working on. A page registers its surface while
 * mounted (and clears it with null on unmount); the dock reads it with useSurface().
 */
import { useSyncExternalStore } from 'react';
import type { ActionResult, Check, FlowGraph } from '../api/types';
import type { Proposal } from '../api/modeler';

export interface FlowSurface {
  kind: 'flow'; flowId: number; name: string; template: string; org: string; canEdit: boolean; draftVer: number | null;
  graph(): FlowGraph;                 // the current working graph
  flush(): Promise<void>;             // save a pending autosave first
  showProposal(p: Proposal | null): void;           // draw dashed on the canvas, or clear
  applyGraph(g: FlowGraph, nodeId: string | null, call: () => Promise<ActionResult<{ checks: Check[] }>>): Promise<boolean>;
  select(nodeId: string | null, tab?: 'inspector' | 'history'): void;
}
export type Surface = FlowSurface | { kind: 'compose'; id: number | null; org: string; pack: string };

let current: Surface | null = null;
const listeners = new Set<() => void>();

export function registerSurface(s: Surface | null): void {
  current = s;
  listeners.forEach((l) => l());
}

export const currentSurface = (): Surface | null => current;

export function onSurfaceChange(l: () => void): () => void {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

export function useSurface(): Surface | null {
  return useSyncExternalStore(onSurfaceChange, currentSurface, currentSurface);
}
