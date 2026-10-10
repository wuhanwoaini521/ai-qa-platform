import React, { useRef } from 'react';
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
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const views: { id: SidebarTab; label: string; count?: number }[] = [
    { id: 'files', label: t('sidebarView.files') },
    { id: 'tests', label: t('sidebarView.testsShort'), count: testCount },
    { id: 'git', label: t('sidebarView.gitShort'), count: changeCount },
    { id: 'pr', label: t('sidebarView.prShort') },
  ];

  return (
    <div className="studio-view-switcher" role="tablist" aria-label={t('sidebarView.switcherLabel')}>
      {views.map((view, index) => (
        <button
          key={view.id}
          ref={(element) => { tabRefs.current[index] = element; }}
          id={`studio-sidebar-tab-${view.id}`}
          type="button"
          role="tab"
          aria-controls="studio-sidebar-panel"
          aria-selected={sidebarTab === view.id}
          tabIndex={sidebarTab === view.id ? 0 : -1}
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
          onKeyDown={(event) => {
            const offset = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
            const targetIndex = event.key === 'Home'
              ? 0
              : event.key === 'End'
                ? views.length - 1
                : offset
                  ? (index + offset + views.length) % views.length
                  : -1;
            if (targetIndex < 0) return;
            event.preventDefault();
            onSelectTab(views[targetIndex].id);
            tabRefs.current[targetIndex]?.focus();
          }}
        >
          {view.label}
          {typeof view.count === 'number' && view.count > 0 && <span className="view-count">{view.count}</span>}
        </button>
      ))}
    </div>
  );
};
