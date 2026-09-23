import React, { useEffect, useState } from 'react';
import { AIStatusResponse, Project, RunnerProfile } from '../types';
import { api } from '../api/client';
import { FolderGit2, Sparkles, Cpu } from 'lucide-react';

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
  const [aiStatus, setAiStatus] = useState<AIStatusResponse | null>(null);
  const [runnerProfiles, setRunnerProfiles] = useState<RunnerProfile[]>([]);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const [ai, runners] = await Promise.allSettled([
          api.getAIStatus(),
          api.getRunnerProfiles(selectedProjectId || undefined),
        ]);
        if (ai.status === 'fulfilled') setAiStatus(ai.value);
        if (runners.status === 'fulfilled') setRunnerProfiles(runners.value);
      } catch (err) {
        console.error('Failed to load status in header', err);
      }
    };
    fetchStatus();
  }, [selectedProjectId]);

  return (
    <header className="app-topbar">
      <div className="topbar-title-section">
        <h1 className="topbar-page-title">{title}</h1>
        {projects.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <FolderGit2 size={14} color="#64748b" />
            <select
              className="form-control"
              style={{ width: '200px', padding: '4px 8px', fontSize: '12px' }}
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

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        {/* AI Health Badge */}
        {aiStatus && (
          <div
            title={`AI Provider: ${aiStatus.provider} (${aiStatus.model}) - ${aiStatus.status}`}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
              fontSize: '11px',
              padding: '3px 8px',
              borderRadius: '12px',
              background: aiStatus.status === 'AVAILABLE' ? '#eff6ff' : '#fef2f2',
              color: aiStatus.status === 'AVAILABLE' ? '#1d4ed8' : '#b91c1c',
              border: `1px solid ${aiStatus.status === 'AVAILABLE' ? '#bfdbfe' : '#fecaca'}`,
            }}
          >
            <Sparkles size={12} color={aiStatus.status === 'AVAILABLE' ? '#2563eb' : '#dc2626'} />
            <span style={{ fontWeight: 600 }}>AI: {aiStatus.provider}</span>
          </div>
        )}

        {/* Runner Indicator */}
        <div
          title={`Runner Profiles: ${runnerProfiles.length} configured`}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '5px',
            fontSize: '11px',
            padding: '3px 8px',
            borderRadius: '12px',
            background: '#f8fafc',
            color: '#475569',
            border: '1px solid #e2e8f0',
          }}
        >
          <Cpu size={12} color="#64748b" />
          <span>Runners: {runnerProfiles.length > 0 ? `${runnerProfiles.length} Active` : 'Local'}</span>
        </div>

        <div className="topbar-actions">{actions}</div>
      </div>
    </header>
  );
};
