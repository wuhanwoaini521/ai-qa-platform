import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Activity, Check, Globe, LayoutDashboard, Play, RefreshCw, RotateCcw, Wifi } from 'lucide-react';
import { SUPPORTED_LANGUAGES } from '../i18n';
import { START_PAGE_OPTIONS, usePreferences } from '../app/Preferences';
import { useProjectScope } from '../app/ProjectScope';
import { buildProjectDisplayNames } from '../app/projectSelectionModel';
import './SettingsPage.css';
import { api } from '../api/client';
import type {
  AIProviderConnectionResult,
  AIStatusResponse,
  ConfigReloadResult,
  DecisionResult,
  EffectiveConfigResponse,
  JevRuntimeCheckResult,
} from '../types';
import { AIHealthPanel } from '../components/AIHealthPanel';

const defaultPlayState = '{\n  "example": "value"\n}';
const defaultPlayOptions = 'approve | Accept the proposed action\nreject | Reject the proposed action\nunknown | Not enough information';

function ConfigField({ label, value }: { label: string; value: string | number | boolean }) {
  return (
    <div>
      <div className="form-label">{label}</div>
      <div style={{ fontSize: 13, overflowWrap: 'anywhere' }}>{String(value)}</div>
    </div>
  );
}

function ConfigGrid({ children }: { children: React.ReactNode }) {
  return <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 14 }}>{children}</div>;
}

export const SettingsPage: React.FC = () => {
  const { t } = useTranslation('settings');
  const { theme, setTheme, language, setLanguage, startPage, setStartPage, defaultProjectId, setDefaultProjectId, reset } =
    usePreferences();
  const { projects } = useProjectScope();
  const projectDisplayNames = buildProjectDisplayNames(projects);
  const [effective, setEffective] = useState<EffectiveConfigResponse | null>(null);
  const [sources, setSources] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [reloading, setReloading] = useState(false);
  const [reloadResult, setReloadResult] = useState<ConfigReloadResult | null>(null);
  const [configError, setConfigError] = useState('');
  const [aiStatus, setAiStatus] = useState<AIStatusResponse | null>(null);
  const [aiConnection, setAiConnection] = useState<AIProviderConnectionResult | null>(null);
  const aiTestVersion = useRef(0);
  const [testingAI, setTestingAI] = useState(false);
  const [jevConnection, setJevConnection] = useState<{ connected: boolean; message: string; detail?: string } | null>(null);
  const [testingJev, setTestingJev] = useState(false);
  const [jevRuntime, setJevRuntime] = useState<JevRuntimeCheckResult | null>(null);
  const [checkingJevRuntime, setCheckingJevRuntime] = useState(false);
  const [playState, setPlayState] = useState(defaultPlayState);
  const [playOptions, setPlayOptions] = useState(defaultPlayOptions);
  const [decision, setDecision] = useState<DecisionResult | null>(null);
  const [runningDecision, setRunningDecision] = useState(false);
  const [playError, setPlayError] = useState('');

  const loadEffective = async () => {
    setConfigError('');
    const [configResult, sourceResult] = await Promise.all([api.getEffectiveConfig(), api.getConfigSources()]);
    setEffective(configResult);
    setSources(sourceResult.sources);
  };

  useEffect(() => {
    let active = true;
    void Promise.all([api.getEffectiveConfig(), api.getConfigSources()])
      .then(([configResult, sourceResult]) => {
        if (!active) return;
        setEffective(configResult);
        setSources(sourceResult.sources);
        const statusVersion = aiTestVersion.current;
        void api.getAIStatus().then((status) => {
          if (active && statusVersion === aiTestVersion.current) setAiStatus(status);
        }).catch(() => undefined);
      })
      .catch(() => { if (active) setConfigError(t('effective.loadFailed')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [t]);

  const config = effective?.config;
  const parsedOptions = useMemo(() => playOptions.split('\n').map((line) => {
    const separator = line.indexOf('|');
    return separator < 0 ? null : { key: line.slice(0, separator).trim(), description: line.slice(separator + 1).trim() };
  }).filter((option): option is { key: string; description: string } => Boolean(option?.key && option.description)), [playOptions]);

  const reload = async () => {
    setReloading(true);
    setConfigError('');
    setReloadResult(null);
    try {
      const result = await api.reloadConfig();
      setReloadResult(result);
      await loadEffective();
      if (result.applied) void api.getAIStatus().then(setAiStatus).catch(() => undefined);
    } catch {
      setConfigError(t('effective.reloadFailed'));
    } finally {
      setReloading(false);
    }
  };

  const testAI = async () => {
    aiTestVersion.current += 1;
    setTestingAI(true);
    setAiStatus(null);
    setAiConnection(null);
    try {
      setAiConnection(await api.testAIProviderConnection());
    } catch {
      setConfigError(t('aiConfig.connectionFailed'));
    } finally {
      setTestingAI(false);
    }
  };

  const testJev = async () => {
    setTestingJev(true);
    setJevConnection(null);
    try {
      const result = await api.testJevConnection();
      setJevConnection({
        connected: result.connected,
        message: result.message,
        detail: result.connected ? `${result.model ?? config?.jev.model} · ${result.latency_ms ?? 0} ms` : result.code,
      });
    } catch {
      setJevConnection({ connected: false, message: t('jev.connectionFailed') });
    } finally {
      setTestingJev(false);
    }
  };

  const checkJevRuntime = async () => {
    setCheckingJevRuntime(true);
    setJevRuntime(null);
    try {
      setJevRuntime(await api.checkJevRuntime());
    } catch {
      setConfigError(t('jev.runtimeCheckFailed'));
    } finally {
      setCheckingJevRuntime(false);
    }
  };

  const runPlayground = async () => {
    setRunningDecision(true);
    setPlayError('');
    setDecision(null);
    try {
      const state = JSON.parse(playState) as unknown;
      setDecision(await api.chooseDecision({ name: 'settings_playground', state, options: parsedOptions }));
    } catch (error) {
      setPlayError(error instanceof SyntaxError ? t('jev.invalidState') : t('jev.playgroundFailed'));
    } finally {
      setRunningDecision(false);
    }
  };

  return (
    <div className="page-container settings-page">
      <nav className="settings-nav" aria-label={t('sectionNav.title')}>
        <span>{t('sectionNav.title')}</span>
        <a href="#settings-effective">{t('sectionNav.effective')}</a>
        <a href="#settings-ai-health">{t('sectionNav.aiHealth')}</a>
        <a href="#settings-preferences">{t('sectionNav.preferences')}</a>
        <a href="#settings-jev-playground">{t('sectionNav.jevPlayground')}</a>
      </nav>
      <div className="settings-main">
      <section id="settings-effective" className="card settings-effective" style={{ marginBottom: 16 }}>
        <div className="card-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          <span className="card-title">{t('effective.title')}</span>
          <button type="button" className="btn btn-secondary btn-sm" disabled={reloading || loading} onClick={() => void reload()}>
            <RefreshCw size={13} /> {reloading ? t('effective.reloading') : t('effective.reload')}
          </button>
        </div>
        <div className="card-body">
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 0 }}>{t('effective.description')}</p>
          {loading ? <p>{t('aiConfig.loading')}</p> : effective ? <>
            <p style={{ fontSize: 12, overflowWrap: 'anywhere' }}><strong>{t('effective.path')}:</strong> <code>{effective.config_path}</code> · v{effective.schema_version}</p>
            {effective.legacy_database_settings_detected && <p role="status" style={{ color: 'var(--accent-orange)' }}>{t('effective.legacyDatabase')}</p>}
            {reloadResult && <p role="status" style={{ color: reloadResult.applied ? 'var(--accent-green)' : 'var(--accent-orange)' }}>
              {reloadResult.applied ? t('effective.reloaded') : `${t('effective.restartRequired')}: ${reloadResult.restart_required.join(', ')}`}
            </p>}
            {configError && <p role="alert" style={{ color: 'var(--accent-red)' }}>{configError}</p>}
            <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t('effective.runtimeState')}: AI {effective.runtime_state.ai} · Jev {effective.runtime_state.jev} · Repair {effective.runtime_state.repair}</p>
            <div className="card" style={{ marginTop: 16 }}><div className="card-header"><strong>{t('effective.ai')}</strong></div><div className="card-body">
              <ConfigGrid>
                <ConfigField label={t('effective.enabled')} value={config?.ai.enabled ?? false} />
                <ConfigField label={t('effective.provider')} value={config?.ai.provider ?? ''} />
                <ConfigField label={t('effective.model')} value={config?.ai.model ?? ''} />
                <ConfigField label={t('effective.timeout')} value={`${config?.ai.timeout_seconds ?? 0}s`} />
                <ConfigField label={t('aiConfig.maxRetries')} value={config?.ai.retries ?? 0} />
                <ConfigField label={t('effective.budget')} value={`${config?.ai.budget.max_request_tokens ?? 0} tokens / ${config?.ai.budget.max_daily_requests ?? 0} calls/day`} />
                <ConfigField label={t('effective.apiKey')} value={config?.ai.api_key === '***' ? t('effective.secretConfiguredOrEmpty') : t('effective.secretHidden')} />
              </ConfigGrid>
              {aiStatus && <div className={`ai-runtime-status is-${aiStatus.status.toLowerCase()}`} role="status" style={{ marginTop: 14 }}>
                <strong>{t(`aiConfig.status_${aiStatus.status}`)}</strong><span>{aiStatus.provider} · {aiStatus.model}</span>
                {aiStatus.message && <span>{aiStatus.message}</span>}
                <small>{t(`health.states.${aiStatus.operational_state}`, { defaultValue: aiStatus.operational_state })} · {Math.round(aiStatus.latency_ms ?? 0)} ms</small>
              </div>}
              <button type="button" className="btn btn-secondary btn-sm" disabled={testingAI} onClick={() => void testAI()} style={{ marginTop: 12 }}>
                <Wifi size={13} /> {testingAI ? t('aiConfig.testing') : t('aiConfig.testConnection')}
              </button>
              {aiConnection && <p role="status" style={{ color: aiConnection.connected && aiConnection.structured_output_supported !== false ? 'var(--accent-green)' : 'var(--accent-red)', fontSize: 12 }}>
                {aiConnection.message} · {aiConnection.provider} / {aiConnection.model} · {Math.round(aiConnection.latency_ms ?? 0)} ms
              </p>}
            </div></div>
            <div className="card" style={{ marginTop: 12 }}><div className="card-header"><strong>{t('effective.jev')}</strong></div><div className="card-body">
              <ConfigGrid>
                <ConfigField label={t('effective.enabled')} value={config?.jev.enabled ?? false} />
                <ConfigField label={t('effective.model')} value={config?.jev.model ?? ''} />
                <ConfigField label={t('effective.apiKey')} value={config?.jev.api_key === '***' ? t('effective.secretConfiguredOrEmpty') : t('effective.secretHidden')} />
                <ConfigField label={t('effective.timeout')} value={`${config?.jev.timeout_seconds ?? 0}s`} />
                <ConfigField label={t('effective.retries')} value={config?.jev.retries ?? 0} />
                <ConfigField label={t('jev.minimumConfidence')} value={config?.jev.minimum_confidence ?? 0} />
                <ConfigField label={t('effective.requireJev')} value={config?.repair.require_jev ?? false} />
                <ConfigField label={t('effective.fallback')} value={config?.jev.failure_policy.allow_local_fallback ? t('effective.allowed') : t('effective.blocked')} />
              </ConfigGrid>
              <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                <button type="button" className="btn btn-secondary btn-sm" disabled={testingJev} onClick={() => void testJev()}><Wifi size={13} /> {testingJev ? t('jev.testing') : t('jev.testConnection')}</button>
                <button type="button" className="btn btn-secondary btn-sm" disabled={checkingJevRuntime} onClick={() => void checkJevRuntime()}><Activity size={13} /> {checkingJevRuntime ? t('jev.checkingRuntime') : t('jev.checkRuntime')}</button>
              </div>
              {jevConnection && <p role="status" style={{ color: jevConnection.connected ? 'var(--accent-green)' : 'var(--accent-red)', fontSize: 12 }}>{jevConnection.message} · {jevConnection.detail}</p>}
              {jevRuntime && <p role="status" style={{ fontSize: 12 }}>{t('jev.runtime')}: {t(`jev.runtime_${jevRuntime.runtime}`)} · {t(`jev.connectivity_${jevRuntime.connectivity}`)} · {jevRuntime.reasons.join(', ')}</p>}
            </div></div>
            <div className="card" style={{ marginTop: 12 }}><div className="card-header"><strong>{t('effective.repair')}</strong></div><div className="card-body"><ConfigGrid>
              <ConfigField label={t('effective.mode')} value={config?.repair.mode ?? 'OFF'} />
              <ConfigField label={t('effective.autoStart')} value={config?.repair.auto_start_on_failure ?? false} />
              <ConfigField label={t('effective.autoRollback')} value={config?.repair.auto_rollback ?? false} />
              <ConfigField label={t('effective.requireJev')} value={config?.repair.require_jev ?? false} />
            </ConfigGrid><p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 12 }}>{t('effective.approvalBoundary')}</p></div></div>
            <div className="card" style={{ marginTop: 12 }}><div className="card-header"><strong>{t('effective.browser')}</strong></div><div className="card-body"><ConfigGrid>
              <ConfigField label={t('effective.timeout')} value={`${config?.browser.timeout_seconds ?? 0}s`} />
              <ConfigField label={t('effective.navigationTimeout')} value={`${config?.browser.navigation_timeout_seconds ?? 0}s`} />
              <ConfigField label={t('effective.sessionIdle')} value={`${config?.browser.session_idle_timeout_seconds ?? 0}s`} />
              <ConfigField label={t('effective.viewport')} value={`${config?.browser.viewport_width ?? 0} × ${config?.browser.viewport_height ?? 0}`} />
            </ConfigGrid></div></div>
            <div className="card" style={{ marginTop: 12 }}><div className="card-header"><strong>{t('effective.run')}</strong></div><div className="card-body"><ConfigGrid>
              <ConfigField label={t('effective.timeout')} value={`${config?.run.default_timeout_seconds ?? 0}s`} />
              <ConfigField label={t('effective.maxParallelRuns')} value={config?.run.max_parallel_runs ?? 0} />
              <ConfigField label={t('effective.pytestWorkers')} value={config?.pytest.workers ?? 0} />
              <ConfigField label={t('effective.pytestTimeout')} value={`${config?.pytest.timeout_seconds ?? 0}s`} />
            </ConfigGrid></div></div>
            <details style={{ marginTop: 16 }}><summary>{t('effective.sourceDetails')}</summary><pre style={{ maxHeight: 280, overflow: 'auto', fontSize: 11 }}>{JSON.stringify(sources, null, 2)}</pre></details>
            <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t('effective.secretNote')}</p>
          </> : configError && <p role="alert" style={{ color: 'var(--accent-red)' }}>{configError}</p>}
        </div>
      </section>

      <div id="settings-ai-health"><AIHealthPanel onAIStatusChange={setAiStatus} /></div>

      <section id="settings-preferences" className="card" style={{ marginBottom: 16 }}>
        <div className="card-header"><span className="card-title">{t('title')}</span></div>
        <div className="card-body">
          <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t('subtitle')}</p>
          <div style={{ marginBottom: 20 }}>
            <label className="form-label" htmlFor="settings-theme">{t('theme')}</label>
            <select id="settings-theme" className="form-control" style={{ maxWidth: 280 }} value={theme} onChange={(event) => setTheme(event.target.value as typeof theme)}>
              <option value="system">{t('themeSystem')}</option><option value="light">{t('themeLight')}</option><option value="dark">{t('themeDark')}</option>
            </select>
          </div>
          <div style={{ marginBottom: 20 }}>
            <label className="form-label" htmlFor="settings-language"><Globe size={13} style={{ verticalAlign: '-2px', marginRight: 6 }} />{t('common:language')}</label>
            <select id="settings-language" className="form-control" style={{ maxWidth: 280 }} value={language} onChange={(event) => setLanguage(event.target.value as (typeof SUPPORTED_LANGUAGES)[number]['code'])}>
              {SUPPORTED_LANGUAGES.map((entry) => <option key={entry.code} value={entry.code}>{entry.label}</option>)}
            </select>
          </div>
          <div style={{ marginBottom: 20 }}>
            <label className="form-label" htmlFor="settings-start-page"><LayoutDashboard size={13} style={{ verticalAlign: '-2px', marginRight: 6 }} />{t('startPage')}</label>
            <select id="settings-start-page" className="form-control" style={{ maxWidth: 280 }} value={startPage} onChange={(event) => setStartPage(event.target.value)}>
              {START_PAGE_OPTIONS.map((option) => <option key={option.path} value={option.path}>{t(option.labelKey)}</option>)}
            </select>
          </div>
          <div>
            <label className="form-label" htmlFor="settings-default-project">{t('defaultProject')}</label>
            <select id="settings-default-project" className="form-control" style={{ maxWidth: 280 }} value={defaultProjectId ?? ''} onChange={(event) => setDefaultProjectId(event.target.value || null)}>
              <option value="">{t('defaultProjectNone')}</option>
              {projects.map((project) => <option key={project.id} value={project.id}>{projectDisplayNames.get(project.id) ?? project.name}</option>)}
            </select>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 20 }}>
            <span style={{ fontSize: 12, color: 'var(--accent-green)' }}><Check size={13} style={{ verticalAlign: '-2px', marginRight: 4 }} />{t('saved')}</span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={reset}><RotateCcw size={13} /> {t('common:reset')}</button>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 12 }}>{t('storageNote')}</div>
        </div>
      </section>

      <section id="settings-jev-playground" className="card" style={{ marginBottom: 16 }}>
        <div className="card-header"><span className="card-title">{t('jev.playgroundTitle')}</span></div>
        <div className="card-body">
          <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t('jev.playgroundDescription')}</p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
            <div><label className="form-label" htmlFor="decision-state">{t('jev.stateJson')}</label><textarea id="decision-state" className="form-control" rows={7} value={playState} onChange={(event) => setPlayState(event.target.value)} /></div>
            <div><label className="form-label" htmlFor="decision-options">{t('jev.options')}</label><textarea id="decision-options" className="form-control" rows={7} value={playOptions} onChange={(event) => setPlayOptions(event.target.value)} /></div>
          </div>
          <button type="button" className="btn btn-primary btn-sm" disabled={runningDecision || parsedOptions.length < 2} onClick={() => void runPlayground()} style={{ marginTop: 12 }}><Play size={13} /> {runningDecision ? t('jev.running') : t('jev.run')}</button>
          {playError && <p role="alert" style={{ color: 'var(--accent-red)' }}>{playError}</p>}
          {decision && <pre style={{ fontSize: 12, overflow: 'auto' }}>{JSON.stringify(decision, null, 2)}</pre>}
        </div>
      </section>
      </div>
    </div>
  );
};
