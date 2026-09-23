import React from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
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
          <div
            key={tab.path}
            className={`studio-tab ${isActive ? 'is-active' : ''}`}
            onClick={() => onSelectTab(tab.path)}
          >
            {tab.isDirty && <span className="tab-dot" aria-hidden="true" />}
            <span className="studio-tab-name">{tab.name}</span>
            <button className="studio-tab-close" onClick={(e) => onCloseTab(tab.path, e)}>
              <X size={12} />
            </button>
          </div>
        );
      })}
      {tabs.length === 0 && !showDiffView && (
        <span style={{ fontSize: '12px', color: 'var(--ui-ink-muted)' }}>{t('tabs.noOpenTabs')}</span>
      )}
    </div>
  );
};
