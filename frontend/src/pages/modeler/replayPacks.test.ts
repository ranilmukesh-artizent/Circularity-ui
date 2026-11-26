import { describe, expect, it, vi } from 'vitest';
import type { ModelerScreen } from '../../api/types';

vi.mock('../../api/session', () => ({ can: () => true, currentAccount: () => ({ role: 'Planner' }) }));

import { NO_REPLAY_PACKS, showReplay } from './ReplayPanel';

const screen = (key: string) => ({ template: { key } }) as unknown as ModelerScreen;

describe('the Replay panel across packs', () => {
  it('shows for every pack but the industrial one', () => {
    for (const key of ['tool_fleet', 'device', 'used_cars', 'telecom_network', 'medical_rental', 'itad']) {
      expect(showReplay(screen(key))).toBe(true);
    }
    expect(NO_REPLAY_PACKS).toEqual(['industrial']);
    expect(showReplay(screen('industrial'))).toBe(false);
  });
});
