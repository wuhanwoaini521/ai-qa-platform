import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Globe, LayoutDashboard, RotateCcw, Save, Wifi } from 'lucide-react';
import { SUPPORTED_LANGUAGES } from '../i18n';
import { START_PAGE_OPTIONS, usePreferences } from '../app/Preferences';
import { useProjectScope } from '../app/ProjectScope';
import { api } from '../api/client';
import type { AIProviderConnectionResult, AIProviderSettings, AIProviderSettingsUpdate, AIStatusResponse, DecisionResult, JevSettings, JevSettingsUpdate } from '../types';

const defaultAISettings: AIProviderSettings = {
  provider: 'fake',
  api_key_configured: false,
  api_key_masked: null,
  model: 'gpt-4o-mini',
  base_url: 'https://api.openai.com/v1',
  timeout: 30,
  max_retries: 3,
};

const defaultJevSettings: JevSettings = {
  enabled: false,
  api_key_configured: false,
  api_key_masked: null,
  model: 'jev-1.13.0',
  base_url: 'https://api.typesafe.ai/v1/systemone',
  timeout: 20,
  minimum_confidence: 0.6,
};

/** Settings page for server-backed AI providers and browser-local interface preferences. */
export const SettingsPage: React.FC = () => {
  const { t } = useTranslation('settings');
  const { language, setLanguage, startPage, setStartPage, defaultProjectId, setDefaultProjectId, reset } =
    usePreferences();
  const { projects } = useProjectScope();
  const [jev, setJev] = useState<JevSettings>(defaultJevSettings);
  const [aiSettings, setAiSettings] = useState<AIProviderSettings>(defaultAISettings);
  const [aiStatus, setAiStatus] = useState<AIStatusResponse | null>(null);
  const [aiApiKey, setAiApiKey] = useState('');
  const [loadingAI, setLoadingAI] = useState(true);
  const [savingAI, setSavingAI] = useState(false);
  const [testingAI, setTestingAI] = useState(false);
  const [aiMessage, setAiMessage] = useState('');
  const [aiConnection, setAiConnection] = useState<AIProviderConnectionResult | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [loadingJev, setLoadingJev] = useState(true);
  const [savingJev, setSavingJev] = useState(false);
  const [testingJev, setTestingJev] = useState(false);
  const [jevMessage, setJevMessage] = useState('');
  const [connection, setConnection] = useState<{ connected: boolean; message: string; detail?: string } | null>(null);
  const [playState, setPlayState] = useState('{\n  "example": "value"\n}');
  const [playOptions, setPlayOptions] = useState('approve | Accept the proposed action\nreject | Reject the proposed action\nunknown | Not enough information');
  const [decision, setDecision] = useState<DecisionResult | null>(null);
  const [runningDecision, setRunningDecision] = useState(false);
  const [playError, setPlayError] = useState('');

  useEffect(() => {
    let active = true;
    api.getJevSettings().then((value) => {
      if (active) setJev(value);
    }).catch(() => {
      if (active) setJevMessage(t('jev.loadFailed'));
    }).finally(() => {
      if (active) setLoadingJev(false);
    });
    return () => { active = false; };
  }, [t]);

  useEffect(() => {
    let active = true;
    api.getAIProviderSettings().then((value) => {
      if (active) setAiSettings(value);
    }).catch(() => {
      if (active) setAiMessage(t('aiConfig.loadFailed'));
    }).finally(() => {
      if (active) setLoadingAI(false);
    });
    return () => { active = false; };
  }, [t]);

  useEffect(() => {
    let active = true;
    api.getAIStatus().then((value) => { if (active) setAiStatus(value); }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  const aiPayload = (clearKey = false): AIProviderSettingsUpdate => ({
    provider: aiSettings.provider,
    api_key: aiApiKey || undefined,
    clear_api_key: clearKey,
    model: aiSettings.model,
    base_url: aiSettings.base_url,
    timeout: Number(aiSettings.timeout),
    max_retries: Number(aiSettings.max_retries),
  });

  const saveAI = async (clearKey = false) => {
    setSavingAI(true);
    setAiMessage('');
    try {
      const saved = await api.saveAIProviderSettings(aiPayload(clearKey));
      setAiSettings(saved);
      void api.getAIStatus().then(setAiStatus).catch(() => undefined);
      setAiApiKey('');
      setAiMessage(t(clearKey ? 'aiConfig.keyCleared' : 'aiConfig.saved'));
    } catch {
      setAiMessage(t('aiConfig.saveFailed'));
    } finally {
      setSavingAI(false);
    }
  };

  const testAI = async () => {
    setTestingAI(true);
    setAiMessage('');
    setAiConnection(null);
    try {
      setAiConnection(await api.testAIProviderConnection(aiPayload()));
    } catch {
      setAiMessage(t('aiConfig.connectionFailed'));
    } finally {
      setTestingAI(false);
    }
  };

  const parsedOptions = useMemo(() => playOptions.split('\n').map((line) => {
    const separator = line.indexOf('|');
    return separator < 0 ? null : { key: line.slice(0, separator).trim(), description: line.slice(separator + 1).trim() };
  }).filter((option): option is { key: string; description: string } => Boolean(option?.key && option.description)), [playOptions]);

  const jevPayload = (clearKey = false): JevSettingsUpdate => ({
    enabled: jev.enabled,
    api_key: apiKey || undefined,
    clear_api_key: clearKey,
    model: jev.model,
    base_url: jev.base_url,
    timeout: Number(jev.timeout),
    minimum_confidence: Number(jev.minimum_confidence),
  });

  const saveJev = async (clearKey = false) => {
    setSavingJev(true);
    setJevMessage('');
    try {
      const saved = await api.saveJevSettings(jevPayload(clearKey));
      setJev(saved);
      setApiKey('');
      setJevMessage(t(clearKey ? 'jev.keyCleared' : 'jev.saved'));
    } catch {
      setJevMessage(t('jev.saveFailed'));
    } finally {
      setSavingJev(false);
    }
  };

  const testJev = async () => {
    setTestingJev(true);
    setConnection(null);
    try {
      const result = await api.testJevConnection(jevPayload());
      setConnection({
        connected: result.connected,
        message: result.message,
        detail: result.connected ? `${result.model ?? jev.model} · ${result.latency_ms ?? 0} ms · ${result.choice ?? ''}` : result.code,
      });
    } catch {
      setConnection({ connected: false, message: t('jev.connectionFailed') });
    } finally {
      setTestingJev(false);
    }
  };

  const runPlayground = async () => {
    setRunningDecision(true);
    setPlayError('');
    setDecision(null);
    try {
      const state = JSON.parse(playState) as unknown;
      const result = await api.chooseDecision({ name: 'settings_playground', state, options: parsedOptions });
      setDecision(result);
    } catch (error) {
      setPlayError(error instanceof SyntaxError ? t('jev.invalidState') : t('jev.playgroundFailed'));
    } finally {
      setRunningDecision(false);
    }
  };

  return (
    <div className="page-container settings-page">
      <div className="card" style={{ marginBottom: '16px' }}>
        <div className="card-header"><span className="card-title">{t('aiConfig.title')}</span></div>
        <div className="card-body">
          <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '16px' }}>{t('aiConfig.description')}</p>
          {aiStatus && <div className={`ai-runtime-status is-${aiStatus.status.toLowerCase()}`} role="status">
            <strong>{t(`aiConfig.status_${aiStatus.status}`)}</strong>
            <span>{aiStatus.provider} · {aiStatus.model}</span>
            {aiStatus.failure_reason && <code>{aiStatus.failure_reason}</code>}
            <small>{aiStatus.fallback_active ? t('aiConfig.fallbackActive') : t('aiConfig.realProviderStatus')}</small>
          </div>}
          {loadingAI ? <p>{t('aiConfig.loading')}</p> : <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '12px' }}>
              <div>
                <label className="form-label" htmlFor="ai-provider">{t('aiConfig.provider')}</label>
                <select id="ai-provider" className="form-control" value={aiSettings.provider} onChange={(event) => setAiSettings({ ...aiSettings, provider: event.target.value as AIProviderSettings['provider'] })}>
                  <option value="fake">{t('aiConfig.fakeProvider')}</option>
                  <option value="openai-compatible">{t('aiConfig.openAICompatibleProvider')}</option>
                </select>
              </div>
              <div>
                <label className="form-label" htmlFor="ai-api-key">{t('aiConfig.apiKey')}</label>
                <input id="ai-api-key" className="form-control" type="password" autoComplete="new-password" value={aiApiKey} onChange={(event) => setAiApiKey(event.target.value)} placeholder={aiSettings.api_key_configured ? t('aiConfig.keyConfigured') : t('aiConfig.apiKeyPlaceholder')} />
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>{t('aiConfig.secretNote')}</div>
              </div>
              <div>
                <label className="form-label" htmlFor="ai-model">{t('aiConfig.model')}</label>
                <input id="ai-model" className="form-control" value={aiSettings.model} onChange={(event) => setAiSettings({ ...aiSettings, model: event.target.value })} />
              </div>
              <div style={{ gridColumn: '1 / -1' }}>
                <label className="form-label" htmlFor="ai-base-url">{t('aiConfig.baseUrl')}</label>
                <input id="ai-base-url" className="form-control" value={aiSettings.base_url} onChange={(event) => setAiSettings({ ...aiSettings, base_url: event.target.value })} />
              </div>
              <div>
                <label className="form-label" htmlFor="ai-timeout">{t('aiConfig.timeout')}</label>
                <input id="ai-timeout" className="form-control" type="number" min="1" max="300" value={aiSettings.timeout} onChange={(event) => setAiSettings({ ...aiSettings, timeout: Number(event.target.value) })} />
              </div>
              <div>
                <label className="form-label" htmlFor="ai-retries">{t('aiConfig.maxRetries')}</label>
                <input id="ai-retries" className="form-control" type="number" min="0" max="10" value={aiSettings.max_retries} onChange={(event) => setAiSettings({ ...aiSettings, max_retries: Number(event.target.value) })} />
              </div>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '16px' }}>
              <button type="button" className="btn btn-primary btn-sm" disabled={savingAI} onClick={() => void saveAI()}><Save size={13} /> {savingAI ? t('aiConfig.saving') : t('aiConfig.save')}</button>
              <button type="button" className="btn btn-secondary btn-sm" disabled={testingAI} onClick={() => void testAI()}><Wifi size={13} /> {testingAI ? t('aiConfig.testing') : t('aiConfig.testConnection')}</button>
              {aiSettings.api_key_configured && <button type="button" className="btn btn-secondary btn-sm" disabled={savingAI} onClick={() => void saveAI(true)}>{t('aiConfig.clearKey')}</button>}
            </div>
            {aiMessage && <p role="status" style={{ fontSize: '12px', marginTop: '12px' }}>{aiMessage}</p>}
            {aiConnection && <p role="status" style={{ color: aiConnection.connected ? 'var(--success-color, #16a34a)' : 'var(--danger-color, #dc2626)', fontSize: '12px', marginTop: '12px' }}>{aiConnection.message} · {aiConnection.provider} / {aiConnection.status}</p>}
          </>}
        </div>
      </div>

      <div className="card" style={{ marginBottom: '16px' }}>
        <div className="card-header">
          <span className="card-title">{t('title')}</span>
        </div>
        <div className="card-body">
          <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '16px' }}>
            {t('subtitle')}
          </p>

          {/* Language */}
          <div style={{ marginBottom: '20px' }}>
            <label className="form-label" htmlFor="settings-language">
              <Globe size={13} style={{ verticalAlign: '-2px', marginRight: '6px' }} />
              {t('common:language')}
            </label>
            <select
              id="settings-language"
              className="form-control"
              style={{ maxWidth: '280px' }}
              value={language}
              onChange={(e) => setLanguage(e.target.value as (typeof SUPPORTED_LANGUAGES)[number]['code'])}
            >
              {SUPPORTED_LANGUAGES.map((entry) => (
                <option key={entry.code} value={entry.code}>
                  {entry.label}
                </option>
              ))}
            </select>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
              {t('common:languageDescription')}
            </div>
          </div>

          {/* Start page */}
          <div style={{ marginBottom: '20px' }}>
            <label className="form-label" htmlFor="settings-start-page">
              <LayoutDashboard size={13} style={{ verticalAlign: '-2px', marginRight: '6px' }} />
              {t('startPage')}
            </label>
            <select
              id="settings-start-page"
              className="form-control"
              style={{ maxWidth: '280px' }}
              value={startPage}
              onChange={(e) => setStartPage(e.target.value)}
            >
              {START_PAGE_OPTIONS.map((option) => (
                <option key={option.path} value={option.path}>
                  {t(option.labelKey)}
                </option>
              ))}
            </select>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
              {t('startPageDescription')}
            </div>
          </div>

          {/* Default project */}
          <div>
            <label className="form-label" htmlFor="settings-default-project">
              {t('defaultProject')}
            </label>
            <select
              id="settings-default-project"
              className="form-control"
              style={{ maxWidth: '280px' }}
              value={defaultProjectId ?? ''}
              onChange={(e) => setDefaultProjectId(e.target.value || null)}
            >
              <option value="">{t('defaultProjectNone')}</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
              {t('defaultProjectDescription')}
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '20px' }}>
            <span style={{ fontSize: '12px', color: 'var(--success-color, #16a34a)' }}>
              <Check size={13} style={{ verticalAlign: '-2px', marginRight: '4px' }} />
              {t('saved')}
            </span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={reset}>
              <RotateCcw size={13} /> {t('common:reset')}
            </button>
          </div>

          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '12px' }}>{t('storageNote')}</div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: '16px' }}>
        <div className="card-header"><span className="card-title">{t('jev.title')}</span></div>
        <div className="card-body">
          <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '16px' }}>{t('jev.description')}</p>
          {loadingJev ? <p>{t('jev.loading')}</p> : <>
            <label style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '16px' }}>
              <input type="checkbox" checked={jev.enabled} onChange={(event) => setJev({ ...jev, enabled: event.target.checked })} />
              <span>{t('jev.enabled')}</span>
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '12px' }}>
              <div>
                <label className="form-label" htmlFor="jev-api-key">{t('jev.apiKey')}</label>
                <input id="jev-api-key" className="form-control" type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={jev.api_key_configured ? t('jev.keyConfigured') : t('jev.apiKeyPlaceholder')} />
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>{t('jev.secretNote')}</div>
              </div>
              <div>
                <label className="form-label" htmlFor="jev-model">{t('jev.model')}</label>
                <input id="jev-model" className="form-control" value={jev.model} onChange={(event) => setJev({ ...jev, model: event.target.value })} />
              </div>
              <div style={{ gridColumn: '1 / -1' }}>
                <label className="form-label" htmlFor="jev-base-url">{t('jev.baseUrl')}</label>
                <input id="jev-base-url" className="form-control" value={jev.base_url} onChange={(event) => setJev({ ...jev, base_url: event.target.value })} />
              </div>
              <div>
                <label className="form-label" htmlFor="jev-timeout">{t('jev.timeout')}</label>
                <input id="jev-timeout" className="form-control" type="number" min="1" max="300" step="1" value={jev.timeout} onChange={(event) => setJev({ ...jev, timeout: Number(event.target.value) })} />
              </div>
              <div>
                <label className="form-label" htmlFor="jev-confidence">{t('jev.minimumConfidence')}</label>
                <input id="jev-confidence" className="form-control" type="number" min="0" max="1" step="0.01" value={jev.minimum_confidence} onChange={(event) => setJev({ ...jev, minimum_confidence: Number(event.target.value) })} />
              </div>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '16px' }}>
              <button type="button" className="btn btn-primary btn-sm" disabled={savingJev} onClick={() => void saveJev()}><Save size={13} /> {savingJev ? t('jev.saving') : t('jev.save')}</button>
              <button type="button" className="btn btn-secondary btn-sm" disabled={testingJev} onClick={() => void testJev()}><Wifi size={13} /> {testingJev ? t('jev.testing') : t('jev.testConnection')}</button>
              {jev.api_key_configured && <button type="button" className="btn btn-secondary btn-sm" disabled={savingJev} onClick={() => void saveJev(true)}>{t('jev.clearKey')}</button>}
            </div>
            {jevMessage && <p role="status" style={{ fontSize: '12px', marginTop: '12px' }}>{jevMessage}</p>}
            {connection && <p role="status" style={{ color: connection.connected ? 'var(--success-color, #16a34a)' : 'var(--danger-color, #dc2626)', fontSize: '12px', marginTop: '12px' }}>{connection.message}{connection.detail ? ` · ${connection.detail}` : ''}</p>}
          </>}
        </div>
      </div>

      <div className="card">
        <div className="card-header"><span className="card-title">{t('jev.playgroundTitle')}</span></div>
        <div className="card-body">
          <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '16px' }}>{t('jev.playgroundDescription')}</p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '12px' }}>
            <div><label className="form-label" htmlFor="jev-play-state">{t('jev.stateJson')}</label><textarea id="jev-play-state" className="form-control" rows={7} value={playState} onChange={(event) => setPlayState(event.target.value)} /></div>
            <div><label className="form-label" htmlFor="jev-play-options">{t('jev.options')}</label><textarea id="jev-play-options" className="form-control" rows={7} value={playOptions} onChange={(event) => setPlayOptions(event.target.value)} /><div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>{t('jev.optionsHelp')}</div></div>
          </div>
          <button type="button" className="btn btn-primary btn-sm" style={{ marginTop: '12px' }} disabled={runningDecision || parsedOptions.length < 2} onClick={() => void runPlayground()}>{runningDecision ? t('jev.running') : t('jev.run')}</button>
          {playError && <p role="alert" style={{ color: 'var(--danger-color, #dc2626)', fontSize: '12px' }}>{playError}</p>}
          {decision && <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', marginTop: '12px', padding: '12px', background: 'var(--surface-subtle, #f8fafc)', borderRadius: '6px', fontSize: '12px' }}>{JSON.stringify(decision, null, 2)}</pre>}
        </div>
      </div>
    </div>
  );
};
