export function normalizeTrustedDomains(input: string): string[] {
  const domains: string[] = [];
  for (const item of input.split(/[,，\n]/).map((value) => value.trim()).filter(Boolean)) {
    try {
      const url = new URL(/^[a-z][a-z\d+.-]*:\/\//i.test(item) ? item : `https://${item}`);
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || !url.hostname.includes('.')) continue;
      const hostname = url.hostname.toLowerCase().replace(/\.$/, '').replace(/^www\./, '');
      if (!domains.includes(hostname)) domains.push(hostname);
    } catch {
      // Invalid entries are ignored; the browser task remains unverified without a valid trusted host.
    }
  }
  return domains;
}

function normalizeHttpUrl(value: string): string | null {
  try {
    const candidate = /^(https?:\/\/|about:)/i.test(value.trim()) ? value.trim() : `https://${value.trim()}`;
    const url = new URL(candidate);
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch {
    return null;
  }
}

export function flowStartUrl(goal: string, currentUrl: string): string | null {
  const trimPunctuation = (value: string) => value.replace(/[.,!?，。；、)）]+$/u, '');
  const explicitUrl = goal.match(/https?:\/\/[^\s，。；、<>"'“”‘’]+/iu)?.[0];
  if (explicitUrl) return normalizeHttpUrl(trimPunctuation(explicitUrl)) ?? normalizeHttpUrl(currentUrl);

  const describedUrl = goal.match(/(?:localhost|(?:\d{1,3}\.){3}\d{1,3}|(?:[\p{L}\d-]+\.)+[\p{L}]{2,})(?::\d+)?(?:\/[^\s，。；、<>"'“”‘’]*)?/iu)?.[0];
  return (describedUrl && normalizeHttpUrl(trimPunctuation(describedUrl))) || normalizeHttpUrl(currentUrl);
}

export function isNavigationFrameFresh(observedRevision: number, requiredRevision?: number): boolean {
  return requiredRevision === undefined || observedRevision >= requiredRevision;
}
