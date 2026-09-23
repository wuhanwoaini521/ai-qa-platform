import React from 'react';
import { Project } from '../types';
import { FolderGit2 } from 'lucide-react';

interface HeaderProps {
  title: string;
  projects: Project[];
  selectedProjectId: string | null;
  onSelectProject: (id: string) => void;
  actions?: React.ReactNode;
}

export const Header: React.FC<HeaderProps> = ({
  title,
  projects,
  selectedProjectId,
  onSelectProject,
  actions,
}) => {
  return (
    <header className="app-topbar">
      <div className="topbar-title-section">
        <h1 className="topbar-page-title">{title}</h1>
        {projects.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <FolderGit2 size={14} color="#64748b" />
            <select
              className="form-control"
              style={{ width: '220px', padding: '4px 8px', fontSize: '12px' }}
              value={selectedProjectId || ''}
              onChange={(e) => onSelectProject(e.target.value)}
            >
              <option value="">All Projects</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>
      <div className="topbar-actions">{actions}</div>
    </header>
  );
};
