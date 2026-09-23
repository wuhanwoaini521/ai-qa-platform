import React from 'react';
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
}) => (
  <div className="studio-sidebar-header">
    <span>
      {sidebarTab === 'files' && 'Workspace Files'}
      {sidebarTab === 'tests' && 'Pytest Explorer'}
      {sidebarTab === 'git' && `Git: ${currentBranch}`}
      {sidebarTab === 'pr' && (activePRNumber ? `PR #${activePRNumber}` : 'Pull Request')}
    </span>
    <div style={{ display: 'flex', gap: '4px' }}>
      {sidebarTab === 'files' && (
        <>
          <button className="icon-btn" title="New File" onClick={onNewFile}>
            <FilePlus size={13} />
          </button>
          <button className="icon-btn" title="New Folder" onClick={onNewFolder}>
            <FolderPlus size={13} />
          </button>
        </>
      )}
      {sidebarTab === 'git' && (
        <button className="icon-btn" title="New Branch" onClick={onNewBranch}>
          <Plus size={13} />
        </button>
      )}
      {sidebarTab === 'pr' && activePRNumber !== null && (
        <button
          className="icon-btn"
          title="Refresh Checks"
          disabled={loadingChecks}
          onClick={onRefreshChecks}
        >
          <RefreshCw size={13} className={loadingChecks ? 'spin' : ''} />
        </button>
      )}
      <button className="icon-btn" title="Refresh" onClick={onRefreshAll}>
        <RefreshCw size={13} />
      </button>
    </div>
  </div>
);
