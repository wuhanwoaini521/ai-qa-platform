import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  GitCommit,
  GitPullRequest,
  Plus,
  Sparkles,
  UploadCloud,
} from 'lucide-react';
import { BranchInfo, GitCommitInfo, GitDiffResult } from '../../../types';

interface SourceControlPanelProps {
  currentBranch: string;
  branches: BranchInfo[];
  recentCommits: GitCommitInfo[];
  diffResult: GitDiffResult;
  showDiffView: boolean;
  commitMessage: string;
  isCommitting: boolean;
  isPushing: boolean;
  pushStatusMessage: string | null;
  suggestingCommit: boolean;
  onSwitchBranch: (targetBranch: string) => void;
  onNewBranch: () => void;
  onToggleDiffView: () => void;
  onOpenFile: (path: string) => void;
  onCommitMessageChange: (value: string) => void;
  onSuggestCommit: () => void;
  onCommit: () => void;
  onPush: () => void;
  onOpenPRModal: () => void;
}

export const SourceControlPanel: React.FC<SourceControlPanelProps> = ({
  currentBranch,
  branches,
  recentCommits,
  diffResult,
  showDiffView,
  commitMessage,
  isCommitting,
  isPushing,
  pushStatusMessage,
  suggestingCommit,
  onSwitchBranch,
  onNewBranch,
  onToggleDiffView,
  onOpenFile,
  onCommitMessageChange,
  onSuggestCommit,
  onCommit,
  onPush,
  onOpenPRModal,
}) => {
  const { t } = useTranslation('studioPanels');

  return (
    <div style={{ padding: '8px' }}>
      {/* Branch Selector & Switcher */}
      <div style={{ marginBottom: '10px', padding: '8px', background: 'var(--surface-inset)', borderRadius: 'var(--r-xs)' }}>
        <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--ink-muted)', marginBottom: '4px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span>{t('sourceControl.branch')}</span>
          <button
            className="btn btn-secondary btn-sm"
            style={{ padding: '2px 6px', fontSize: '10px' }}
            onClick={onNewBranch}
          >
            <Plus size={10} /> {t('sourceControl.newBranch')}
          </button>
        </div>
        <select
          className="form-control"
          aria-label={t('sourceControl.branch')}
          style={{ fontSize: '12px', padding: '4px' }}
          value={currentBranch}
          onChange={(e) => onSwitchBranch(e.target.value)}
        >
          {branches.map((b) => (
            <option key={b.name} value={b.name}>
              {b.name} {b.is_current ? t('sourceControl.current') : ''}
            </option>
          ))}
        </select>
        {currentBranch === 'main' && (
          <div style={{ fontSize: '10px', color: 'var(--accent-amber)', marginTop: '4px' }}>
            {t('sourceControl.mainBranchNotePrefix')} <code>qa/...</code> {t('sourceControl.mainBranchNoteSuffix')}
          </div>
        )}
      </div>

      {/* Changed Files Section */}
      <div style={{ marginBottom: '10px' }}>
        <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--ink-muted)', marginBottom: '4px', display: 'flex', justifyContent: 'space-between' }}>
          <span>{t('sourceControl.changes', { count: diffResult.changed_files.length })}</span>
          <button
            style={{ background: 'none', border: 'none', color: 'var(--primary)', cursor: 'pointer', fontSize: '10px' }}
            onClick={onToggleDiffView}
          >
            {showDiffView ? t('sourceControl.hideDiff') : t('sourceControl.viewDiff')}
          </button>
        </div>
        {diffResult.changed_files.length === 0 ? (
          <div style={{ fontSize: '11px', color: 'var(--ink-faint)', fontStyle: 'italic', padding: '4px 0' }}>
            {t('sourceControl.noChanges')}
          </div>
        ) : (
          <div style={{ maxHeight: '110px', overflowY: 'auto', border: '1px solid var(--line-strong)', borderRadius: 'var(--r-xs)', padding: '4px' }}>
            {diffResult.changed_files.map((cf, idx) => (
              <div
                key={idx}
                style={{
                  fontSize: '11px',
                  fontFamily: 'var(--font-mono)',
                  padding: '2px 4px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  cursor: 'pointer',
                }}
                onClick={() => onOpenFile(cf.path)}
              >
                <span style={{ color: cf.status === 'M' ? 'var(--accent-amber)' : 'var(--accent-green)', fontWeight: 700 }}>
                  {cf.status}
                </span>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {cf.path}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Commit Actions */}
      <div style={{ marginBottom: '10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
          <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--ink-muted)' }}>{t('sourceControl.commit')}</span>
          <button
            className="btn btn-secondary btn-sm"
            style={{ padding: '2px 6px', fontSize: '10px', gap: '3px' }}
            disabled={suggestingCommit}
            onClick={onSuggestCommit}
            title={t('sourceControl.aiSuggestTitle')}
          >
            <Sparkles size={10} color="var(--accent-violet)" /> {suggestingCommit ? '...' : t('sourceControl.aiSuggest')}
          </button>
        </div>
        <textarea
          rows={2}
          className="form-control"
          style={{ fontSize: '11px', padding: '4px', resize: 'none', marginBottom: '4px' }}
          placeholder={t('sourceControl.commitPlaceholder')}
          value={commitMessage}
          onChange={(e) => onCommitMessageChange(e.target.value)}
        />
        <button
          className="btn btn-primary btn-sm"
          style={{ width: '100%', padding: '4px', fontSize: '11px' }}
          disabled={!commitMessage.trim() || isCommitting}
          onClick={onCommit}
        >
          <GitCommit size={12} /> {isCommitting ? t('sourceControl.committing') : t('sourceControl.commitChanges')}
        </button>
      </div>

      {/* Push Branch */}
      <div style={{ marginBottom: '12px' }}>
        <button
          className="btn btn-secondary btn-sm"
          style={{ width: '100%', padding: '4px', fontSize: '11px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}
          disabled={isPushing}
          onClick={onPush}
        >
          <UploadCloud size={13} color="var(--accent-blue)" /> {isPushing ? t('sourceControl.pushing') : t('sourceControl.pushBranch', { branch: currentBranch })}
        </button>
        {pushStatusMessage && (
          <div style={{ fontSize: '10px', color: 'var(--ink-muted)', marginTop: '4px', background: 'var(--surface-inset)', padding: '4px', borderRadius: 'var(--r-xs)' }}>
            {pushStatusMessage}
          </div>
        )}
      </div>

      {/* Create PR Shortcut */}
      <div style={{ marginBottom: '12px', borderTop: '1px solid var(--line-strong)', paddingTop: '8px' }}>
        <button
          className="btn btn-primary btn-sm"
          style={{ width: '100%', padding: '5px', fontSize: '11px', background: 'var(--accent-green)', borderColor: 'var(--accent-green)' }}
          onClick={onOpenPRModal}
        >
          <GitPullRequest size={13} /> {t('sourceControl.createPR')}
        </button>
      </div>

      {/* Recent Commits Log */}
      <div>
        <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--ink-muted)', marginBottom: '4px' }}>
          {t('sourceControl.recentCommits')}
        </div>
        <div style={{ maxHeight: '120px', overflowY: 'auto' }}>
          {recentCommits.length === 0 ? (
            <div style={{ fontSize: '10px', color: 'var(--ink-faint)' }}>{t('sourceControl.noCommits')}</div>
          ) : (
            recentCommits.map((c) => (
              <div
                key={c.sha}
                style={{
                  padding: '4px 6px',
                  borderBottom: '1px solid var(--surface-inset)',
                  fontSize: '11px',
                }}
              >
                <div style={{ fontWeight: 600, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {c.message}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '9px', color: 'var(--ink-muted)' }}>
                  <code>{c.sha.slice(0, 7)}</code>
                  <span>{c.date.slice(0, 10)}</span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
