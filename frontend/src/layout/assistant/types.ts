import type { ComponentType } from 'react';

/** Plan 10 section 5: the contracts every assistant task (T1-T7) codes against. Types only. */
export type AssistantMode = 'ask' | 'change' | 'setup';
export interface AssistantContext {
  page: string; section?: string; caseId?: string; role: string;
  flow?: { id: number; name: string; template: string; org: string; canEdit: boolean; draftVer: number | null };
  pack?: string; org?: string;
}
export interface OpenRequest { mode?: AssistantMode; question?: string; composeId?: number }
export type TurnState = 'waiting' | 'working' | 'done' | 'held' | 'blocked' | 'failed' | 'stopped';
export interface Status { verb: string; item: string; limit?: string; state: TurnState }
export interface Turn { id: number; mode: AssistantMode; text: string; status: Status[]; data: unknown; error?: string }
export interface ModeDef {
  id: AssistantMode; label: string; placeholder: string; limits(ctx: AssistantContext): string;
  /** null when available, else why not (shown on the disabled radio) */
  unavailable(ctx: AssistantContext): string | null;
  send(text: string, ctx: AssistantContext, io: { signal: AbortSignal; patch(f: (t: Turn) => Turn): void }): Promise<void>;
  Turn: ComponentType<{ turn: Turn; ctx: AssistantContext; ask(text: string, mode?: AssistantMode): void }>;
  Empty: ComponentType<{ ctx: AssistantContext; ask(text: string, mode?: AssistantMode): void }>;
}
