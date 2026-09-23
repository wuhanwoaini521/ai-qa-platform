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

/** Segmented control: one rounded track, the active view is a raised pill with a pixel dot. */
export const SidebarViewSwitcher: React.FC<SidebarViewSwitcherProps> = ({
  sidebarTab,
  testCount,
  changeCount,
  activePRNumber,
  onSelectTab,
}) => {
  const { t } = useTranslation('studioShell');

  const views: { id: SidebarTab; label: string; count?: number }[] = [
    { id: 'files', label: t('sidebarView.files') },
    { id: 'tests', label: t('sidebarView.testsShort'), count: testCount },
    { id: 'git', label: t('sidebarView.gitShort'), count: changeCount },
    { id: 'pr', label: t('sidebarView.prShort') },
  ];

  return (
    <div className="studio-view-switcher" role="tablist">
      {views.map((view) => (
        <button
          key={view.id}
          type="button"
          role="tab"
          aria-selected={sidebarTab === view.id}
          className={sidebarTab === view.id ? 'is-active' : ''}
          title={
            view.id === 'git'
              ? t('sidebarView.git', { changeCount })
              : view.id === 'tests'
                ? t('sidebarView.tests', { testCount })
                : view.id === 'pr' && activePRNumber
                  ? `PR #${activePRNumber}`
                  : view.label
          }
          onClick={() => onSelectTab(view.id)}
        >
          {view.label}
          {typeof view.count === 'number' && view.count > 0 && <span className="view-count">{view.count}</span>}
        </button>
      ))}
    </div>
  );
};
