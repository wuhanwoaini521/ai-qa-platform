import React from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, CheckCircle2, GitBranch, Loader2, Play } from 'lucide-react';

interface WorkbenchStatusBarProps {
  branch: string | null;
  problemCount: number;
  validating: boolean;
  runningTest: boolean;
  saving: boolean;
  activeFileName: string | null;
  language: string | null;
}

/** Slim status bar: the essentials only, with a square pixel state dot. */
export const WorkbenchStatusBar: React.FC<WorkbenchStatusBarProps> = ({
  branch,
  problemCount,
  validating,
  runningTest,
  saving,
  activeFileName,
  language,
}) => {
  const { t } = useTranslation('studioPanels');

  const state = runningTest
    ? { className: 'is-busy', label: t('statusBar.running'), icon: <Play size={11} /> }
    : saving
      ? { className: 'is-busy', label: t('statusBar.saving'), icon: <Loader2 size={11} /> }
      : validating
        ? { className: 'is-busy', label: t('statusBar.validating'), icon: <Loader2 size={11} /> }
        : problemCount > 0
          ? { className: 'is-error', label: t('statusBar.issues', { problemCount }), icon: <AlertTriangle size={11} /> }
          : { className: 'is-idle', label: t('statusBar.ready'), icon: <CheckCircle2 size={11} /> };

  return (
    <div className="studio-statusbar">
      <span className="studio-status-item">
        <span className={`studio-status-dot ${state.className}`} aria-hidden="true" />
        {state.icon}
        {state.label}
      </span>

      {branch && (
        <span className="studio-status-item is-mono">
          <GitBranch size={11} />
          {branch}
        </span>
      )}

      <span className="studio-status-spacer" />

      {activeFileName && (
        <span className="studio-status-item is-mono" title={activeFileName}>
          {activeFileName}
        </span>
      )}
      {language && <span className="studio-status-item">{language}</span>}
      <span className="studio-status-item">{t('statusBar.engine')}</span>
    </div>
  );
};
