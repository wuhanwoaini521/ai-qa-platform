export function recallEntity(projectId: string | null, kind: string): string | null {
  try {return projectId ? sessionStorage.getItem(`ai-qa.journey.${projectId}.${kind}`) : null;} catch {return null;}
}
export function rememberEntity(projectId: string, kind: string, id: string) {
  try {sessionStorage.setItem(`ai-qa.journey.${projectId}.${kind}`,id);} catch { /* deep links remain authoritative */ }
}
