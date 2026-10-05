import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { FailureRecord } from '../../types';
import {
  availableEvidenceTabs,
  extractRelevantFrames,
  normalizeFailureClassification,
  summarizeFailureError,
  type EvidenceTab,
} from './failureWorkspaceModel';

const tabOrder: EvidenceTab[] = [
  'SUMMARY',
  'SOURCE',
  'STACK',
  'BROWSER',
  'CONSOLE',
  'NETWORK',
  'ARTIFACTS',
];

function valueText(value: unknown): string {
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}

export const FailureEvidence: React.FC<{
  failure: FailureRecord;
  environment?: Record<string, string>;
  browser?: string;
}> = ({ failure, environment, browser }) => {
  const { t } = useTranslation('failures');
  const tabs = availableEvidenceTabs(failure);
  const [activeTab, setActiveTab] = useState<EvidenceTab>('SUMMARY');
  useEffect(() => setActiveTab('SUMMARY'), [failure.id]);
  const visibleTab = tabs.includes(activeTab) ? activeTab : 'SUMMARY';

  const bundle = failure.evidence_bundle ?? {};
  const relevantFrames = extractRelevantFrames(failure.stack_trace);
  const errorSummary = summarizeFailureError(failure.error_message);
  const isUnconfirmedEnvironmentHint =
    errorSummary === 'browserLaunchEperm' &&
    normalizeFailureClassification(failure.classification) === 'UNKNOWN';
  const platform = Object.entries(environment ?? {}).find(([key]) =>
    /(^|_)(os|platform|operating_system)(_|$)/i.test(key),
  )?.[1];
  const handleTabKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft' && event.key !== 'Home' && event.key !== 'End') return;
    event.preventDefault();
    const current = tabs.indexOf(visibleTab);
    const next = event.key === 'Home'
      ? tabs[0]
      : event.key === 'End'
        ? tabs.at(-1)!
        : tabs[(current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length];
    setActiveTab(next);
    document.getElementById(`failure-evidence-tab-${next.toLowerCase()}`)?.focus();
  };

  const renderTab = () => {
    switch (visibleTab) {
      case 'SUMMARY':
        return (
          <div className="failure-evidence-summary">
            <strong>{t(`summary.${errorSummary === 'browserLaunchEperm' ? 'browserLaunch' : errorSummary === 'timeout' ? 'timeout' : errorSummary === 'assertion' ? 'assertion' : 'generic'}`, { detail: errorSummary })}</strong>
            {isUnconfirmedEnvironmentHint && (
              <p className="failure-heuristic-note" role="note">
                <span>{t('heuristicUnconfirmed')}</span>
                <span>{t('summary.environmentHint')}</span>
              </p>
            )}
            {relevantFrames.length > 0 && (
              <div className="failure-evidence-frames">
                <span>{t('relevantFrames')}</span>
                <ul>
                  {relevantFrames.map((frame) => <li key={frame}><code>{frame}</code></li>)}
                </ul>
              </div>
            )}
            <div className="failure-evidence-facts">
              {browser && <span>{browser}</span>}
              {platform && <span>{platform}</span>}
              {/spawn\s+EPERM/i.test(failure.error_message) && <span>EPERM</span>}
              {failure.failing_locator && <span>{t('failedLocatorRecorded')}</span>}
            </div>
          </div>
        );
      case 'SOURCE': {
        const source = bundle.source_context ?? bundle.context_paths ?? bundle.source;
        return <pre className="failure-evidence-code">{valueText(source)}</pre>;
      }
      case 'STACK':
        return (
          <div>
            {relevantFrames.length > 0 ? (
              <div className="failure-evidence-frames">
                <span>{t('relevantFrames')}</span>
                <ul>{relevantFrames.map((frame) => <li key={frame}><code>{frame}</code></li>)}</ul>
              </div>
            ) : <p className="failure-evidence-empty">{t('noRelevantFrames')}</p>}
            <details className="failure-raw-details">
              <summary>{t('viewFullStack')}</summary>
              <pre className="failure-evidence-code">{failure.stack_trace}</pre>
            </details>
          </div>
        );
      case 'BROWSER':
        return (
          <dl className="failure-evidence-metadata">
            {Boolean(browser || bundle.browser) && <div><dt>{t('browser')}</dt><dd>{browser || valueText(bundle.browser)}</dd></div>}
            {platform && <div><dt>{t('environment')}</dt><dd>{platform}</dd></div>}
            {typeof bundle.page_url === 'string' && <div><dt>{t('pageUrl')}</dt><dd>{bundle.page_url}</dd></div>}
            {failure.screenshot_path && <div><dt>{t('screenshot')}</dt><dd><code>{failure.screenshot_path}</code></dd></div>}
            {failure.dom_snapshot_path && <div><dt>{t('domSnapshot')}</dt><dd><code>{failure.dom_snapshot_path}</code></dd></div>}
          </dl>
        );
      case 'CONSOLE':
        return <pre className="failure-evidence-code">{(failure.console_logs?.length ? failure.console_logs : Array.isArray(bundle.console) ? bundle.console.map(valueText) : bundle.console ? [valueText(bundle.console)] : []).join('\n')}</pre>;
      case 'NETWORK':
        return <pre className="failure-evidence-code">{valueText(bundle.network)}</pre>;
      case 'ARTIFACTS': {
        const paths = [failure.screenshot_path, failure.trace_path, failure.dom_snapshot_path].filter(Boolean);
        const extra = bundle.artifacts;
        return (
          <ul className="failure-artifact-list">
            {paths.map((path) => <li key={path}><code>{path}</code></li>)}
            {Boolean(extra) && <li><pre className="failure-evidence-code">{valueText(extra)}</pre></li>}
          </ul>
        );
      }
    }
  };

  return (
    <section className="card failure-evidence-card" aria-labelledby="failure-evidence-heading">
      <div className="card-header">
        <span className="card-title" id="failure-evidence-heading">{t('evidenceWorkspace')}</span>
      </div>
      <div className="card-body">
        <div className="failure-evidence-tabs" role="tablist" aria-orientation="horizontal" aria-label={t('evidenceWorkspace')}>
          {tabOrder.filter((tab) => tabs.includes(tab)).map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              id={`failure-evidence-tab-${tab.toLowerCase()}`}
              aria-selected={visibleTab === tab}
              aria-controls="failure-evidence-panel"
              tabIndex={visibleTab === tab ? 0 : -1}
              className={`failure-evidence-tab${visibleTab === tab ? ' is-active' : ''}`}
              onClick={() => setActiveTab(tab)}
              onKeyDown={handleTabKeyDown}
            >
              {t(`evidenceTabs.${tab}`)}
            </button>
          ))}
        </div>
        <div
          id="failure-evidence-panel"
          role="tabpanel"
          aria-labelledby={`failure-evidence-tab-${visibleTab.toLowerCase()}`}
          className="failure-evidence-panel"
        >
          {renderTab()}
        </div>
        <details className="failure-raw-details">
          <summary>{t('viewRawError')}</summary>
          <pre className="failure-evidence-code">{failure.error_message}</pre>
        </details>
        {Object.keys(bundle).length > 0 && (
          <details className="failure-raw-details">
            <summary>{t('evidenceBundle')}</summary>
            <pre className="failure-evidence-code">{JSON.stringify(bundle, null, 2)}</pre>
          </details>
        )}
      </div>
    </section>
  );
};
