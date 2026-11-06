import React from 'react';
import { useTranslation } from 'react-i18next';
import { Download, Plus, Sparkles } from 'lucide-react';
import { Project } from '../../../types';

interface RequirementToolbarProps {
  projects: Project[];
  onOpenJira: () => void;
  onNewRequirement: () => void;
  onAnalyze?: () => void;
  analysisRunning?: boolean;
  showEntryActions?: boolean;
}

export const RequirementToolbar: React.FC<RequirementToolbarProps> = ({
  projects,
  onOpenJira,
  onNewRequirement,
  onAnalyze,
  analysisRunning = false,
  showEntryActions = true,
}) => {
  const { t } = useTranslation('requirements');
  const { t: lifecycleT } = useTranslation('lifecycle');
  return (
    <div className="requirement-toolbar" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
      <div className="requirement-toolbar-heading">
        <h2 style={{ fontSize: '18px', fontWeight: 700 }}>{t('toolbarTitle')}</h2>
        <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
          {t('toolbarSubtitle')}
        </p>
      </div>
      <div className="requirement-toolbar-actions" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        {showEntryActions && <>
        <button
          className={`ds-btn btn btn-secondary${onAnalyze ? ' ds-btn-sm btn-sm' : ''}`}
          disabled={projects.length === 0}
          onClick={onOpenJira}
          title={t('toolbarImportFromJiraHint')}
        >
          <Download size={15} /> {t('toolbarImportFromJira')}
        </button>
        <button
          className={`ds-btn btn ${onAnalyze ? 'btn-secondary ds-btn-sm btn-sm' : 'ds-btn-primary btn-primary'}`}
          disabled={projects.length === 0}
          onClick={onNewRequirement}
        >
          <Plus size={16} /> {t('toolbarNewRequirement')}
        </button>
        </>}
        {onAnalyze && <button type="button" className="ds-btn-primary ds-btn-sm ds-btn btn btn-primary btn-sm" disabled={analysisRunning} onClick={onAnalyze}>
          <Sparkles size={14} aria-hidden="true" /> {lifecycleT(analysisRunning ? 'analyzing' : 'analyze')}
        </button>}
      </div>
    </div>
  );
};
