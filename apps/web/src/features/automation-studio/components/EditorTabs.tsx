import React from 'react';
import { useTranslation } from 'react-i18next';
import { FileCode2, X } from 'lucide-react';
import { IconButton } from '@self/ui-style/react';
import { EditorTab } from '../types';

interface EditorTabsProps {
  tabs: EditorTab[];
  activeTabPath: string | null;
  showDiffView: boolean;
  onSelectTab: (path: string) => void;
  onCloseTab: (path: string, e?: React.MouseEvent) => void;
}

/** Rounded tab chips; a square pixel dot marks an unsaved buffer. */
export const EditorTabs: React.FC<EditorTabsProps> = ({
  tabs,
  activeTabPath,
  showDiffView,
  onSelectTab,
  onCloseTab,
}) => {
  const { t } = useTranslation('studioShell');
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '4px', overflowX: 'auto', flex: 1 }}>
      {tabs.map((tab) => {
        const isActive = tab.path === activeTabPath && !showDiffView;
        return (
          <div key={tab.path} className={`studio-tab ${isActive ? 'is-active' : ''}`} title={tab.path}>
            <button type="button" className="ds-btn studio-tab-select" aria-pressed={isActive} onClick={() => onSelectTab(tab.path)}>
              <FileCode2 size={14} aria-hidden="true" />
              {tab.isDirty && <span className="tab-dot" aria-hidden="true" />}
              <span className="studio-tab-name">{tab.name}</span>
            </button>
            <IconButton type="button" className="studio-tab-close" aria-label={t('tabs.closeFile', { fileName: tab.name })} onClick={(e) => onCloseTab(tab.path, e)}>
              <X size={12} />
            </IconButton>
          </div>
        );
      })}
      {tabs.length === 0 && !showDiffView && (
        <span style={{ fontSize: '12px', color: 'var(--ui-ink-muted)' }}>{t('tabs.noOpenTabs')}</span>
      )}
    </div>
  );
};
