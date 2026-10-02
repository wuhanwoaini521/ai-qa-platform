export function parseEventFrame(frame: string): { type: string; data: string; id?: string } | null {
  const data: string[] = [];
  let type = 'message';
  let id: string | undefined;
  for (const line of frame.split(/\r?\n/)) {
    if (!line || line.startsWith(':')) continue;
    const separator = line.indexOf(':');
    const field = separator < 0 ? line : line.slice(0, separator);
    const value = separator < 0 ? '' : line.slice(separator + 1).replace(/^ /, '');
    if (field === 'data') data.push(value);
    else if (field === 'event') type = value || 'message';
    else if (field === 'id' && !value.includes('\0')) id = value;
  }
  return data.length ? { type, data: data.join('\n'), id } : null;
}
