import React from 'react';
import { useTranslation } from 'react-i18next';
import { Download, Plus } from 'lucide-react';
import { Project } from '../../../types';

interface RequirementToolbarProps {
  projects: Project[];
  onOpenJira: () => void;
  onNewRequirement: () => void;
}

export const RequirementToolbar: React.FC<RequirementToolbarProps> = ({
  projects,
  onOpenJira,
  onNewRequirement,
}) => {
  const { t } = useTranslation('requirements');
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
      <div>
        <h2 style={{ fontSize: '18px', fontWeight: 700 }}>{t('toolbarTitle')}</h2>
        <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
          {t('toolbarSubtitle')}
        </p>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <button
          className="btn btn-secondary"
          disabled={projects.length === 0}
          onClick={onOpenJira}
          title={t('toolbarImportFromJiraHint')}
        >
          <Download size={15} /> {t('toolbarImportFromJira')}
        </button>
        <button
          className="btn btn-primary"
          disabled={projects.length === 0}
          onClick={onNewRequirement}
        >
          <Plus size={16} /> {t('toolbarNewRequirement')}
        </button>
      </div>
    </div>
  );
};
