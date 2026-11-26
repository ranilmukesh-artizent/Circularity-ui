/**
 * The dock host of the one assistant (plan 10, 2.2): Ctrl+J toggles it, openAssistant() opens it from anywhere. At 1280px
 * and wider it pushes the page (body.afpon, the app's margin-right); below that it overlays; below 700px it is full
 * screen. While the Modeler's pinned column is mounted this renders nothing: Ctrl+J and every launcher focus the pinned
 * composer instead, so there is never a second copy. This component is always mounted (App), so it owns the listeners.
 */
import { useEffect, useRef, useSyncExternalStore } from 'react';
import { useOverlay } from '../../components/Overlay';
import { onOpenAssistant } from '../../utils/askBus';
import { AssistantPanel } from './AssistantPanel';
import {
  effectiveMode, focusPinned, hasPinned, isOpen, pickMode, reveal, send, setComposeId, setOpen, stop, useConv, useUi,
} from './store';
import { useAssistantContext } from './useAssistantContext';

const WIDE = '(min-width: 1280px)';

const wide = {
  subscribe(l: () => void) {
    const m = window.matchMedia(WIDE);
    m.addEventListener('change', l);
    return () => m.removeEventListener('change', l);
  },
  get: () => window.matchMedia(WIDE).matches,
};

export function AssistantDock() {
  const ui = useUi();
  const ctx = useAssistantContext();
  const isWide = useSyncExternalStore(wide.subscribe, wide.get, () => false);
  const visible = ui.open && ui.pinned === 0;

  // the latest context for the listeners below, which subscribe once
  const latest = useRef(ctx);
  useEffect(() => {
    latest.current = ctx;
  });

  // Ctrl+J / Cmd+J: toggle the dock, or focus the pinned composer
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'j') {
        e.preventDefault();
        if (hasPinned()) focusPinned();
        else setOpen(!isOpen());
      }
    };
    document.addEventListener('keydown', key);
    return () => document.removeEventListener('keydown', key);
  }, []);

  // openAssistant({ mode, question, composeId }) from the top bar, a page launcher, or openAsk(). The composition is part
  // of the context the modes read (Set up names it), so it is set before the question is sent.
  useEffect(
    () =>
      onOpenAssistant((req) => {
        reveal();
        setComposeId(req.composeId ?? null);
        if (req.mode) pickMode(req.mode);
        const ctx = req.composeId != null && latest.current.composeId == null ? { ...latest.current, composeId: req.composeId } : latest.current;
        if (req.question) send(req.question, req.mode ?? effectiveMode(ctx), ctx);
      }),
    [],
  );

  // the page makes room for the docked panel
  useEffect(() => {
    const on = visible && isWide;
    document.body.classList.toggle('afpon', on);
    return () => document.body.classList.remove('afpon');
  }, [visible, isWide]);

  return visible ? <DockHost docked={isWide} /> : null;
}

/** Mounted only while the dock is open: Esc (through the overlay stack) and returning focus to the opener. */
function DockHost({ docked }: { docked: boolean }) {
  const opener = useRef<Element | null>(document.activeElement);
  const conv = useConv();
  const running = conv.running !== null;
  // Esc stops a running turn first, else closes; it never also closes a dialog under the dock
  useOverlay(() => (running ? stop() : setOpen(false)));
  useEffect(
    () => () => {
      const o = opener.current;
      if (o instanceof HTMLElement && o.isConnected) o.focus({ preventScroll: true });
    },
    [],
  );
  return (
    <div className={'as-dockwrap' + (docked ? ' docked' : '')}>
      <AssistantPanel host="dock" onClose={() => setOpen(false)} />
    </div>
  );
}
