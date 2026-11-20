/** Save a file to the viewer's computer. */
export function download(file: string, text: string, type = 'application/json') {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = file;
  a.click();
  window.setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
