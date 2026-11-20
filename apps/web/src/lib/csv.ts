/** Client-side CSV download (the demo's buildCsv). */
export function downloadCsv(text: string, name: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** "value" with inner quotes doubled. */
export const q = (v: unknown): string => `"${String(v).replace(/"/g, '""')}"`;
