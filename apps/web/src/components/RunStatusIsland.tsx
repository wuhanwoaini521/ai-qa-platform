import React from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowUpRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { buildWorkflowHref } from '../app/workspaceContext';
import type { WorkspaceContext } from '../app/workspaceContext';
import { useRunStore } from '../features/runs/useRunStore';

interface RunStatusIslandProps {
  context: WorkspaceContext;
}

type RunStatusTone = 'queued' | 'running' | 'passed' | 'failed' | 'neutral';

function toneForRunStatus(status: string): RunStatusTone {
  switch (status.toUpperCase()) {
    case 'QUEUED':
      return 'queued';
    case 'RUNNING':
      return 'running';
    case 'PASSED':
      return 'passed';
    case 'FAILED':
    case 'ERROR':
      return 'failed';
    default:
      return 'neutral';
  }
}

/** A compact, URL-selected projection of the shared TestRun store. */
export const RunStatusIsland: React.FC<RunStatusIslandProps> = ({ context }) => {
  const runId = context.runId;
  const { run, error } = useRunStore(runId ?? null);
  const { t } = useTranslation('workspace');

  if (!runId) return null;

  const selectedRun = run?.id === runId ? run : null;
  const statusLabel = selectedRun
    ? t(`result.runStatus.${selectedRun.status}`, { defaultValue: selectedRun.status })
    : error
      ? t('runtime.statusUnavailable')
      : t('runtime.loadingRun');
  const tone = selectedRun ? toneForRunStatus(selectedRun.status) : 'neutral';
  const destination = buildWorkflowHref({
    projectId: context.projectId,
    runId,
    parentRunId: context.parentRunId,
    taskId: context.taskId,
    failureId: context.failureId,
    stage: context.failureId ? 'failure' : 'result',
    view: 'results',
  });
  const accessibleLabel = `${t('runtime.openWorkflow')}: ${runId} — ${statusLabel}`;
  const visibleRunId = runId.length > 12 ? `${runId.slice(0, 8)}…` : runId;

  return (
    <Link
      className="run-status-island"
      to={destination}
      aria-label={accessibleLabel}
      title={accessibleLabel}
      data-run-status={selectedRun?.status.toLowerCase() ?? (error ? 'unavailable' : 'loading')}
    >
      <span className={`run-status-island-dot is-${tone}`} aria-hidden="true" />
      <span className="run-status-island-id">{visibleRunId}</span>
      <span className="run-status-island-separator" aria-hidden="true">·</span>
      <span className="run-status-island-state" role="status" aria-live="polite" aria-atomic="true">
        {statusLabel}
      </span>
      <ArrowUpRight size={14} strokeWidth={1.7} aria-hidden="true" />
    </Link>
  );
};
