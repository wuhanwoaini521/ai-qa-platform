import React from 'react';
import { useTranslation } from 'react-i18next';
import { FilePlus, FolderPlus, Plus, RefreshCw } from 'lucide-react';
import { SidebarTab } from '../types';

interface SidebarActionHeaderProps {
  sidebarTab: SidebarTab;
  currentBranch: string;
  activePRNumber: number | null;
  loadingChecks: boolean;
  onNewFile: () => void;
  onNewFolder: () => void;
  onNewBranch: () => void;
  onRefreshChecks: () => void;
  onRefreshAll: () => void;
}

export const SidebarActionHeader: React.FC<SidebarActionHeaderProps> = ({
  sidebarTab,
  currentBranch,
  activePRNumber,
  loadingChecks,
  onNewFile,
  onNewFolder,
  onNewBranch,
  onRefreshChecks,
  onRefreshAll,
}) => {
  const { t } = useTranslation('studioShell');
  return (
    <div className="studio-sidebar-header">
      <span>
        {sidebarTab === 'files' && t('sidebarHeader.workspaceFiles')}
        {sidebarTab === 'tests' && t('sidebarHeader.pytestExplorer')}
        {sidebarTab === 'git' && t('sidebarHeader.git', { branch: currentBranch })}
        {sidebarTab === 'pr' &&
          (activePRNumber ? t('sidebarHeader.prWithNumber', { number: activePRNumber }) : t('sidebarHeader.pullRequest'))}
      </span>
      <div style={{ display: 'flex', gap: '4px' }}>
        {sidebarTab === 'files' && (
          <>
            <button className="icon-btn" title={t('sidebarHeader.newFile')} onClick={onNewFile}>
              <FilePlus size={13} />
            </button>
            <button className="icon-btn" title={t('sidebarHeader.newFolder')} onClick={onNewFolder}>
              <FolderPlus size={13} />
            </button>
          </>
        )}
        {sidebarTab === 'git' && (
          <button className="icon-btn" title={t('sidebarHeader.newBranch')} onClick={onNewBranch}>
            <Plus size={13} />
          </button>
        )}
        {sidebarTab === 'pr' && activePRNumber !== null && (
          <button
            className="icon-btn"
            title={t('sidebarHeader.refreshChecks')}
            disabled={loadingChecks}
            onClick={onRefreshChecks}
          >
            <RefreshCw size={13} className={loadingChecks ? 'spin' : ''} />
          </button>
        )}
        <button className="icon-btn" title={t('common:refresh')} onClick={onRefreshAll}>
          <RefreshCw size={13} />
        </button>
      </div>
    </div>
  );
};
