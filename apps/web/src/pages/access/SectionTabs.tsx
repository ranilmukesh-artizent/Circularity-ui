import { useNavigate } from 'react-router';
import { navigation } from '../../api/nav';

/** The sections of a page the account may see (the demo's navKids), and the one the route asks for (secKey). */
export function sectionsOf(page: string, a: string | null) {
  const g = navigation().find((x) => x.id === page);
  const kids = g?.kids ?? [];
  const key = kids.some((k) => k.id === a) ? (a as string) : kids[0]?.id ?? '';
  return { label: g?.label ?? page, kids, key };
}

/** One section per route, with a tab strip under the page head (the demo's secPage for MCP & Tools and Access). */
export function SectionTabs({ page, a }: { page: string; a: string | null }) {
  const nav = useNavigate();
  const { label, kids, key } = sectionsOf(page, a);
  return (
    <div className="tabs" role="tablist" aria-label={label + ' sections'}>
      {kids.map((k) => (
        <button key={k.id} role="tab" aria-selected={k.id === key} onClick={() => nav('/' + page + '/' + k.id)}>
          {k.label}
        </button>
      ))}
    </div>
  );
}
