// UI audit gap 11: the Connection Fabric's pack systems are shown grouped by pack, in the order the server sends them.
import { describe, expect, it } from 'vitest';
import { groupByPack, type PackSystem } from './packGroups';

const sys = (id: string, pack: string, registered = false): PackSystem => ({ id, name: id.toUpperCase(), vendor: id, type: 't', pack, pack_name: pack + ' name', registered });

describe('groupByPack', () => {
  it('one group per pack in first-seen order, with the pack name and its systems', () => {
    const g = groupByPack([sys('a', 'used_cars'), sys('b', 'used_cars'), sys('c', 'medical_rental')]);
    expect(g.map((x) => x.pack)).toEqual(['used_cars', 'medical_rental']);
    expect(g[0].name).toBe('used_cars name');
    expect(g[0].systems.map((s) => s.id)).toEqual(['a', 'b']);
  });

  it('counts the systems not registered yet and keeps none out', () => {
    const g = groupByPack([sys('a', 'p', true), sys('b', 'p'), sys('c', 'p')]);
    expect(g[0].open).toBe(2);
    expect(g[0].systems).toHaveLength(3);
  });

  it('a pack with every system registered is still listed (the person sees what exists)', () => {
    expect(groupByPack([sys('a', 'p', true)])[0].open).toBe(0);
  });

  it('empty in, empty out', () => expect(groupByPack([])).toEqual([]));
});
