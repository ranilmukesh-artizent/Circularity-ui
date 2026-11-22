/** Connection Fabric's page-wide controls (drawers and dialogs live in the page dispatcher) and who may change sources. */
import { createContext, useContext } from 'react';
import { can } from '../../api/session';

export const canMgr = () => can('manageIntegrations');
export const NOMGR = 'Only the Developer or Admin changes integrations.';

export interface IntUI {
  openSource: (id: string, tab?: string) => void;
  addSource: (cat: string) => void;
  sync: (id: string) => void;
  pause: (id: string) => void;
  disconnect: (id: string) => void;
  reconnect: (id: string) => void;
  remove: (id: string) => void;
  rotate: (id: string) => void;
  connect: (catId: string) => void;
  reauth: (id: string) => void;
  newIntegration: () => void;
  test: (id: string) => void;
  openEvent: (id: string) => void;
  go: (path: string) => void;
}
export const IntCtx = createContext<IntUI | null>(null);
export const useInt = () => useContext(IntCtx)!;
