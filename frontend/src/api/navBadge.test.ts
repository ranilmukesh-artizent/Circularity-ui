import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({ cached: vi.fn() }));
vi.mock('./client', () => ({ cached: m.cached, ref: vi.fn(), session: () => ({}), withQuery: (p: string) => p }));

import { navBadge } from './nav';

beforeEach(() => m.cached.mockReset());

describe('navBadge (plan 9 P9-1.8)', () => {
  it("reads My work's own count from the menu answer", () => {
    m.cached.mockReturnValue({ groups: [], badges: { awaiting: 1, inbox: 2, integration: 0, sections: {}, mywork: 5 }, tasks: 3 });
    expect(navBadge('mywork')).toBe(5);
    expect(navBadge('inbox')).toBe(2);
  });

  it('is 0 when the answer has no such badge', () => {
    m.cached.mockReturnValue({ groups: [], badges: { awaiting: 0, inbox: 0, integration: 0, sections: {} }, tasks: 0 });
    expect(navBadge('mywork')).toBe(0);
  });
});
