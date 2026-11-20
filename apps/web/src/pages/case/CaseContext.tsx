/** The dialogs and side panels a case page can open, shared with its tabs and blocks through context. */
import { createContext, useContext, type ReactNode } from 'react';

/** A dialog or side panel opened from inside a case page (the demo's openModal / openDrawer). */
export interface ModalSpec { title: string; sub?: string; body: ReactNode; foot?: ReactNode; wide?: boolean; drawer?: boolean }

/** The dialogs a case page can open. */
export interface CaseUi {
  openApproval(id: string, mode?: 'review'): void;
  openDecline(id: string): void;
  openExplain(id: string): void;
  modal(m: ModalSpec | null): void;
  go(path: string): void;
}
export const CaseUiContext = createContext<CaseUi | null>(null);
export const useCaseUi = (): CaseUi => useContext(CaseUiContext)!;
