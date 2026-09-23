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
            className={`studio-tab ${isActive ? 'active' : ''}`}
            style={{
              background: isActive ? '#ffffff' : '#f1f5f9',
              borderBottom: isActive ? '2px solid var(--primary)' : 'none',
              fontWeight: isActive ? 600 : 400,
              cursor: 'pointer',
            }}
            onClick={() => onSelectTab(tab.path)}
          >
            <span>{tab.name}</span>
            {tab.isDirty && <span style={{ color: '#ef4444', fontWeight: 700 }}>*</span>}
            <button
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: 0,
                color: 'var(--text-muted)',
                display: 'flex',
              }}
              onClick={(e) => onCloseTab(tab.path, e)}
            >
              <X size={12} />
            </button>
          </div>
        );
      })}
      {tabs.length === 0 && !showDiffView && (
        <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{t('tabs.noOpenTabs')}</span>
      )}
    </div>
  );
};
