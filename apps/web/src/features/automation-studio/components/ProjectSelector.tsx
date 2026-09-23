import React from 'react';
import { Search } from 'lucide-react';
import { Project } from '../../../types';

interface ProjectSelectorProps {
  projects: Project[];
  currentProjectId: string;
  onSelectProject: (id: string) => void;
  onQuickOpen: () => void;
}

export const ProjectSelector: React.FC<ProjectSelectorProps> = ({
  projects,
  currentProjectId,
  onSelectProject,
  onQuickOpen,
}) => (
  <div style={{ padding: '8px 10px', borderBottom: '1px solid var(--border-color)', display: 'flex', gap: '6px' }}>
    <select
      className="form-control"
      style={{ fontSize: '12px', padding: '4px 6px', flex: 1 }}
      value={currentProjectId}
      onChange={(e) => onSelectProject(e.target.value)}
    >
      {projects.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name}
        </option>
      ))}
    </select>
    <button
      className="btn btn-secondary btn-sm"
      style={{ padding: '4px 8px' }}
      title="Quick Open File (Cmd+P)"
      onClick={onQuickOpen}
    >
      <Search size={13} />
    </button>
  </div>
);
