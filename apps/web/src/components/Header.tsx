import React, { useEffect, useState } from 'react';
import { AIStatusResponse, Project, RunnerProfile } from '../types';
import { api } from '../api/client';
import { useTranslation } from 'react-i18next';
import { SUPPORTED_LANGUAGES } from '../i18n';
import { usePreferences } from '../app/Preferences';
import { FolderGit2, Sparkles, Cpu, Languages } from 'lucide-react';

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
  const { t } = useTranslation('common');
  const { language, setLanguage } = usePreferences();
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
              aria-label={t('project')}
              onChange={(e) => onSelectProject(e.target.value)}
            >
              <option value="">{t('allProjects')}</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      <div className="topbar-utility-section" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
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
              background: aiStatus.status === 'REAL_AVAILABLE' ? '#eff6ff' : aiStatus.status === 'FALLBACK_ONLY' ? '#fff7e3' : '#fef2f2',
              color: aiStatus.status === 'REAL_AVAILABLE' ? '#1d4ed8' : aiStatus.status === 'FALLBACK_ONLY' ? '#7c5600' : '#b91c1c',
              border: `1px solid ${aiStatus.status === 'REAL_AVAILABLE' ? '#bfdbfe' : aiStatus.status === 'FALLBACK_ONLY' ? '#e9d7a4' : '#fecaca'}`,
            }}
          >
            <Sparkles size={12} color={aiStatus.status === 'REAL_AVAILABLE' ? '#2563eb' : aiStatus.status === 'FALLBACK_ONLY' ? '#8a5a00' : '#dc2626'} />
            <span style={{ fontWeight: 600 }}>AI: {aiStatus.status} · {aiStatus.provider}</span>
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

        <div
          title={t('languageDescription')}
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
          <Languages size={12} color="#64748b" />
          <select
            aria-label={t('language')}
            value={language}
            onChange={(e) => setLanguage(e.target.value as (typeof SUPPORTED_LANGUAGES)[number]['code'])}
            style={{ border: 'none', background: 'transparent', fontSize: '11px', color: '#475569' }}
          >
            {SUPPORTED_LANGUAGES.map((entry) => (
              <option key={entry.code} value={entry.code}>
                {entry.label}
              </option>
            ))}
          </select>
        </div>

        <div className="topbar-actions">{actions}</div>
      </div>
    </header>
  );
};
