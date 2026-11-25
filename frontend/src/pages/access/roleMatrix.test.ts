import { describe, expect, it } from 'vitest';
import type { RoleMatrix, TestUserResult } from '../../api/access';
import { rowsFor, userCard } from './roleMatrix';

const matrix: RoleMatrix = {
  roles: ['Admin', 'Planner', 'Approver'],
  permissions: [{ perm: 'manageFlows', roles: { Admin: true, Planner: true, Approver: false } }],
  pages: [{ page: 'modeler', roles: { Admin: true, Planner: true } }],
};

describe('P9-0.13 roleMatrix rowsFor', () => {
  it('keeps the role order and fills a missing role with false', () => {
    const { permissions, pages } = rowsFor(matrix);
    expect(permissions[0].cells.map((c) => c.allowed)).toEqual([true, true, false]);
    expect(pages[0].cells).toEqual([
      { role: 'Admin', allowed: true }, { role: 'Planner', allowed: true }, { role: 'Approver', allowed: false },
    ]);
  });
});

const planner: TestUserResult = {
  user_id: 'planner-a', email: 'planner@example.com', found: true, via_group: 'circ-planners-customer-a', source: 'directory', role: 'Planner',
  why: 'Role from group circ-planners-customer-a', account: { id: 'planner-a', label: 'Planner · Customer A' },
  tenants: ['Customer A'], warehouse: null, pages: ['modeler'], permissions: ['manageFlows'], delegations: [], approval_limit: 0, self_approve: false,
};

describe('P9-0.13 roleMatrix userCard', () => {
  it('shows role, why, tenants, pages and permissions', () => {
    const c = userCard(planner);
    expect(c.title).toBe('planner@example.com · Planner');
    expect(c.why).toContain('circ-planners-customer-a');
    const by = Object.fromEntries(c.lines.map((l) => [l.label, l.value]));
    expect(by.Tenants).toBe('Customer A');
    expect(by.Warehouse).toBe('Any');
    expect(by['Approval limit']).toBe('$0');
    expect(by.Pages).toBe('modeler');
  });
  it('a person without an account has no limit shown', () => {
    const c = userCard({ ...planner, account: null, approval_limit: null, tenants: [] });
    const by = Object.fromEntries(c.lines.map((l) => [l.label, l.value]));
    expect(by.Account).toBe('None');
    expect(by['Approval limit']).toBe('No limit');
    expect(by.Tenants).toBe('None');
  });
});
