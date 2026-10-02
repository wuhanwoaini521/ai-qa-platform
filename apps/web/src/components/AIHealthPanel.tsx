import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import type { AIUsageSummary, SystemHealth } from '../types';

export function AIHealthPanel() {
  const { t } = useTranslation('settings');
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [usage, setUsage] = useState<AIUsageSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [feature, setFeature] = useState('');
  const requestSequence = useRef(0);
  const reload = useCallback(async (refresh = false) => {
    const sequence = ++requestSequence.current;
    setLoading(true); setError(false);
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const results = await Promise.allSettled([api.getSystemHealth(refresh), api.getAIUsage(50, today.toISOString(), feature)]);
    if (sequence !== requestSequence.current) return;
    if (results[0].status === 'fulfilled') setHealth(results[0].value);
    if (results[1].status === 'fulfilled') setUsage(results[1].value);
    setError(results.some((result) => result.status === 'rejected')); setLoading(false);
  }, [feature]);
  useEffect(() => {
    const timer = window.setTimeout(() => void reload(), 250);
    return () => { window.clearTimeout(timer); requestSequence.current++; };
  }, [reload]);
  return <div className="card" style={{ marginBottom: 16 }}>
    <div className="card-header"><span className="card-title">{t('health.title')}</span><button className="btn btn-secondary btn-sm" type="button" disabled={loading} onClick={() => void reload(true)}><RefreshCw size={13} />{t('health.refresh')}</button></div>
    <div className="card-body" aria-busy={loading}>
      {error && <p role="alert">{t('health.loadFailed')}</p>}
      {loading && <p role="status">{t('health.loading')}</p>}
      {health && <><p className="text-muted">{t(`health.${health.status}`)} · {new Date(health.checked_at).toLocaleString()}</p><div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 240px), 1fr))', gap: 10 }}>{health.components.map((item) => <div key={item.component} className="card" style={{ padding: 12, minWidth: 0 }}><strong>{t(`health.components.${item.component}`)} · {t(`health.${item.status}`)}</strong><p style={{ fontSize: 12, overflowWrap: 'anywhere', color: 'var(--text-muted)' }}>{item.message}</p><small>{item.operational_state ?? ''} {item.duration_ms} ms</small></div>)}</div></>}
      {usage && <><h3 style={{ marginTop: 20 }}>{t('usage.title')}</h3><p>{t('usage.summary', { total: usage.total_requests, success: usage.successful_requests, failed: usage.failed_requests, fallback: usage.fallback_requests })}</p><p className="text-muted">{t('usage.tokenNote', { input: usage.total_input_tokens, output: usage.total_output_tokens, unknown: usage.unknown_token_requests })}</p>
        <label className="form-label" htmlFor="usage-feature">{t('usage.feature')}</label><input id="usage-feature" className="form-control" value={feature} placeholder={t('usage.allFeatures')} onChange={(event) => setFeature(event.target.value)} />
        <div style={{ overflowX: 'auto', marginTop: 12 }}><table className="data-table"><thead><tr>{['feature', 'provider', 'status', 'duration', 'tokens', 'prompt'].map((key) => <th key={key}>{t(`usage.${key}`)}</th>)}</tr></thead><tbody>{usage.invocations.map((item) => <tr key={item.id}><td>{item.task}</td><td>{item.provider} / {item.model}</td><td>{item.status}{item.fallback_used ? ` · ${t('usage.fallback')}` : ''}{item.error_type ? ` · ${item.error_type}` : ''}</td><td>{Math.round(item.duration_ms)} ms</td><td>{item.token_source === 'provider' ? `${item.input_tokens ?? '?'} / ${item.output_tokens ?? '?'}` : t('usage.unknown')}</td><td>{item.prompt_version ?? '—'}</td></tr>)}{usage.invocations.length === 0 && <tr><td colSpan={6}>{t('usage.empty')}</td></tr>}</tbody></table></div>
        <details style={{ marginTop: 12 }}><summary>{t('usage.byFeature')}</summary>{usage.features.map((item) => <p key={item.feature}>{item.feature} · {item.requests} · {Math.round(item.duration_ms)} ms · {t('usage.fallback')} {item.fallback} · {t('usage.failed')} {item.failed}</p>)}</details>
      </>}
    </div>
  </div>;
}
