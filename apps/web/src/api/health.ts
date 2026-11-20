export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${path}`);
  return res.json() as Promise<T>;
}

export type Check = { ok: boolean; error?: string; [k: string]: unknown };
export type Health = { status: 'ok' | 'degraded'; checks: Record<string, Check> };
