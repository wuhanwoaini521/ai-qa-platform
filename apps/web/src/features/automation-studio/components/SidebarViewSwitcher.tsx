import React from 'react';
import { useTranslation } from 'react-i18next';
import { SidebarTab } from '../types';

interface SidebarViewSwitcherProps {
  sidebarTab: SidebarTab;
  testCount: number;
  changeCount: number;
  activePRNumber: number | null;
  onSelectTab: (tab: SidebarTab) => void;
}

const tabButtonStyle = (active: boolean): React.CSSProperties => ({
  flex: 1,
  padding: '8px 4px',
  fontSize: '10px',
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.5px',
  background: active ? '#ffffff' : 'transparent',
  border: 'none',
  borderBottom: active ? '2px solid var(--primary)' : 'none',
  color: active ? 'var(--primary)' : 'var(--text-muted)',
  cursor: 'pointer',
});

export const SidebarViewSwitcher: React.FC<SidebarViewSwitcherProps> = ({
  sidebarTab,
  testCount,
  changeCount,
  activePRNumber,
  onSelectTab,
}) => {
  const { t } = useTranslation('studioShell');
  return (
    <div style={{ display: 'flex', borderBottom: '1px solid var(--border-color)', background: '#f8fafc' }}>
      <button style={tabButtonStyle(sidebarTab === 'files')} onClick={() => onSelectTab('files')}>
        {t('sidebarView.files')}
      </button>
      <button style={tabButtonStyle(sidebarTab === 'tests')} onClick={() => onSelectTab('tests')}>
        {t('sidebarView.tests', { testCount })}
      </button>
      <button style={tabButtonStyle(sidebarTab === 'git')} onClick={() => onSelectTab('git')}>
        {t('sidebarView.git', { changeCount })}
      </button>
      <button style={tabButtonStyle(sidebarTab === 'pr')} onClick={() => onSelectTab('pr')}>
        {t('sidebarView.pr')} {activePRNumber ? `#${activePRNumber}` : ''}
      </button>
    </div>
  );
};
