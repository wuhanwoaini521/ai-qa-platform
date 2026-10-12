export interface ProjectIdentity {
  id: string;
  name: string;
}

function normalizedName(name: string): string {
  return name.normalize('NFKC').trim().toLowerCase();
}

function uniqueIdSuffix(projectId: string, peers: readonly ProjectIdentity[]): string {
  for (let length = Math.min(6, projectId.length); length <= projectId.length; length += 1) {
    const suffix = projectId.slice(-length);
    if (peers.every((peer) => peer.id === projectId || !peer.id.endsWith(suffix))) return suffix;
  }
  return projectId;
}

export function buildProjectDisplayNames(projects: readonly ProjectIdentity[]): Map<string, string> {
  const groups = new Map<string, ProjectIdentity[]>();
  for (const project of projects) {
    const key = normalizedName(project.name);
    const group = groups.get(key) ?? [];
    group.push(project);
    groups.set(key, group);
  }

  const labels = new Map<string, string>();
  for (const group of groups.values()) {
    for (const project of group) {
      const label = group.length === 1
        ? project.name
        : `${project.name} · #${uniqueIdSuffix(project.id, group)}`;
      labels.set(project.id, label);
    }
  }
  return labels;
}
