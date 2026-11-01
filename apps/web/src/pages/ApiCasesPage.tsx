import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Download, Play, Plus, Save, Trash2 } from 'lucide-react';
import { api } from '../api/client';
import { useProjectScope } from '../app/ProjectScope';
import {
  ApiAssertion,
  ApiCaseDraft,
  ApiHeaderRow,
  RecorderApiCall,
  emptyDraft,
  fromRecorderCall,
  newAssertion,
  newHeader,
  toPayload,
  validateDraft,
} from '../features/api-cases/apiCase';

const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'] as const;

export const ApiCasesPage: React.FC = () => {
  const { t } = useTranslation('apiCase');
  const navigate = useNavigate();
  const { selectedProjectId } = useProjectScope();
  const [baseUrl, setBaseUrl] = useState('');
  const [draft, setDraft] = useState<ApiCaseDraft>(() => emptyDraft());
  const [code, setCode] = useState('');
  const [compileError, setCompileError] = useState('');
  const [message, setMessage] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [calls, setCalls] = useState<RecorderApiCall[]>([]);
  const [importError, setImportError] = useState('');
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    if (!selectedProjectId) {
      setBaseUrl('');
      return;
    }
    let alive = true;
    void api.getProject(selectedProjectId).then((project) => {
      if (alive) setBaseUrl(project.sut_base_url ?? '');
    }).catch(() => {});
    return () => {
      alive = false;
    };
  }, [selectedProjectId]);

  const validation = useMemo(() => validateDraft(draft), [draft]);
  const payload = useMemo(() => {
    try {
      const base = toPayload(draft);
      const url = String(base.url ?? '');
      if (url && !/^https?:\/\//i.test(url) && baseUrl) {
        base.base_url = baseUrl;
      }
      return base;
    } catch {
      return null;
    }
  }, [draft, baseUrl]);

  useEffect(() => {
    if (validation.errors.length > 0 || !payload) {
      setCode('');
      setCompileError('');
      return;
    }
    const timer = window.setTimeout(() => {
      void api
        .compileApiCase(payload)
        .then((result) => {
          setCode(result.code);
          setCompileError('');
        })
        .catch((reason) => {
          setCode('');
          setCompileError(String(reason));
        });
    }, 350);
    return () => window.clearTimeout(timer);
  }, [payload, validation.errors.length]);

  const filePath = `tests/${draft.test_name}.py`;
  const nodeid = `${filePath}::${draft.test_name}`;

  const patch = (next: Partial<ApiCaseDraft>) => setDraft((current) => ({ ...current, ...next }));
  const patchHeader = (id: string, next: Partial<ApiHeaderRow>) =>
    setDraft((current) => ({ ...current, headers: current.headers.map((row) => (row.id === id ? { ...row, ...next } : row)) }));
  const patchAssertion = (id: string, next: Partial<ApiAssertion>) =>
    setDraft((current) => ({
      ...current,
      assertions: current.assertions.map((row) => (row.id === id ? { ...row, ...next } : row)),
    }));

  const importCalls = async () => {
    setImportError('');
    try {
      const result = await api.getRecorderApiCalls(sessionId.trim());
      setCalls(result.calls);
      if (result.calls.length === 0) setImportError(t('noCalls'));
    } catch (reason) {
      setCalls([]);
      setImportError(String(reason));
    }
  };

  const save = async () => {
    if (!selectedProjectId || !code) return;
    setSaving(true);
    setMessage('');
    try {
      await api.writeWorkspaceFile(selectedProjectId, filePath, code);
      setMessage(t('saved', { path: filePath }));
    } catch (reason) {
      setMessage(t('saveFailed', { reason: String(reason) }));
    } finally {
      setSaving(false);
    }
  };

  const run = async () => {
    if (!selectedProjectId || !code) return;
    setRunning(true);
    try {
      const created = await api.createTestRun({
        project_id: selectedProjectId,
        workspace_id: selectedProjectId,
        nodeids: [nodeid],
      });
      navigate(`/runs/${created.id}`);
    } catch (reason) {
      setMessage(t('runFailed', { reason: String(reason) }));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="page-container api-case-page">
      <header className="page-header flow-page-header">
        <div>
          <span className="workspace-eyebrow">{t('eyebrow')}</span>
          <h2>{t('title')}</h2>
          <p className="subtitle">{t('subtitle')}</p>
        </div>
        <nav className="flow-page-actions" aria-label={t('actions')}>
          <button className="btn btn-secondary btn-sm" type="button" onClick={save} disabled={saving || !code || !selectedProjectId}>
            <Save size={14} aria-hidden="true" />
            {saving ? t('saving') : t('save')}
          </button>
          <button className="btn btn-primary btn-sm" type="button" onClick={run} disabled={running || !code || !selectedProjectId}>
            <Play size={14} aria-hidden="true" />
            {running ? t('starting') : t('run')}
          </button>
        </nav>
      </header>

      {(validation.errors.length > 0 || validation.warnings.length > 0) && (
        <section className="flow-editor-messages" role="status">
          {validation.errors.map((key) => (
            <p key={key} className="flow-editor-error">{t(key)}</p>
          ))}
          {validation.warnings.map((key) => (
            <p key={key} className="flow-editor-warning">{t(key)}</p>
          ))}
        </section>
      )}

      <div className="api-case-layout">
        <section className="card api-case-request">
          <h3>{t('request')}</h3>
          <label className="flow-editor-field">
            <span>{t('testName')}</span>
            <input
              className="form-input"
              value={draft.test_name}
              onChange={(event) => patch({ test_name: event.target.value.replace(/[^A-Za-z0-9_]/g, '_') })}
            />
          </label>
          <div className="api-case-url-row">
            <select className="form-select" value={draft.method} onChange={(event) => patch({ method: event.target.value as ApiCaseDraft['method'] })}>
              {METHODS.map((method) => (
                <option key={method} value={method}>{method}</option>
              ))}
            </select>
            <input
              className="form-input"
              placeholder="/api/health or https://host/api/..."
              value={draft.url}
              onChange={(event) => patch({ url: event.target.value })}
            />
          </div>
          <h4>{t('headers')}</h4>
          <div className="api-case-rows">
            {draft.headers.map((header) => (
              <div key={header.id} className="api-case-row">
                <input className="form-input" placeholder="name" value={header.name} onChange={(event) => patchHeader(header.id, { name: event.target.value })} />
                <input className="form-input" placeholder="value" value={header.value} onChange={(event) => patchHeader(header.id, { value: event.target.value })} />
                <button type="button" className="icon-btn" aria-label={t('remove')} onClick={() => patch({ headers: draft.headers.filter((row) => row.id !== header.id) })}>
                  <Trash2 size={14} aria-hidden="true" />
                </button>
              </div>
            ))}
          </div>
          <button className="btn btn-secondary btn-sm" type="button" onClick={() => patch({ headers: [...draft.headers, newHeader()] })}>
            <Plus size={13} aria-hidden="true" />
            {t('addHeader')}
          </button>

          <h4>{t('body')}</h4>
          <label className="api-case-inline">
            <input type="checkbox" checked={draft.useJsonBody} onChange={(event) => patch({ useJsonBody: event.target.checked })} />
            {t('jsonBody')}
          </label>
          <textarea
            className="form-input api-case-body"
            rows={5}
            placeholder={draft.useJsonBody ? '{"sku": "tee", "qty": 2}' : t('bodyPlaceholder')}
            value={draft.body}
            onChange={(event) => patch({ body: event.target.value })}
          />

          <h4>{t('assertions')}</h4>
          <div className="api-case-rows">
            {draft.assertions.map((assertion) => (
              <div key={assertion.id} className="api-case-row">
                <select className="form-select" value={assertion.kind} onChange={(event) => patchAssertion(assertion.id, { kind: event.target.value as ApiAssertion['kind'] })}>
                  <option value="status">{t('assertStatus')}</option>
                  <option value="json_path">{t('assertJsonPath')}</option>
                  <option value="body_contains">{t('assertBody')}</option>
                </select>
                {assertion.kind === 'json_path' && (
                  <input className="form-input" placeholder="data.items[0].id" value={assertion.path} onChange={(event) => patchAssertion(assertion.id, { path: event.target.value })} />
                )}
                <input
                  className="form-input"
                  placeholder={assertion.kind === 'status' ? '200' : t('expected')}
                  value={assertion.expected}
                  onChange={(event) => patchAssertion(assertion.id, { expected: event.target.value })}
                />
                <button type="button" className="icon-btn" aria-label={t('remove')} onClick={() => patch({ assertions: draft.assertions.filter((row) => row.id !== assertion.id) })}>
                  <Trash2 size={14} aria-hidden="true" />
                </button>
              </div>
            ))}
          </div>
          <button className="btn btn-secondary btn-sm" type="button" onClick={() => patch({ assertions: [...draft.assertions, newAssertion('status')] })}>
            <Plus size={13} aria-hidden="true" />
            {t('addAssertion')}
          </button>
        </section>

        <section className="card api-case-preview">
          <header className="flow-editor-preview-head">
            <h3>{t('preview')}</h3>
            <span className="flow-canvas-chip">{filePath}</span>
          </header>
          {message && <p className="flow-editor-save-message">{message}</p>}
          {compileError && <p className="flow-editor-error">{compileError}</p>}
          {code ? <pre className="flow-editor-code">{code}</pre> : <p className="flow-editor-hint">{t('previewPending')}</p>}
        </section>
      </div>

      <section className="card api-case-import">
        <h3>{t('fromRecording')}</h3>
        <p className="flow-editor-hint">{t('fromRecordingHint')}</p>
        <div className="api-case-row">
          <input
            className="form-input"
            placeholder={t('sessionId')}
            value={sessionId}
            onChange={(event) => setSessionId(event.target.value)}
          />
          <button className="btn btn-secondary btn-sm" type="button" onClick={importCalls} disabled={!sessionId.trim()}>
            <Download size={13} aria-hidden="true" />
            {t('loadCalls')}
          </button>
        </div>
        {importError && <p className="flow-editor-error">{importError}</p>}
        {calls.length > 0 && (
          <ul className="api-case-calls">
            {calls.map((call) => (
              <li key={call.id}>
                <span className={`api-case-method is-${call.method.toLowerCase()}`}>{call.method}</span>
                <code>{call.url}</code>
                <span className="flow-canvas-chip">{call.status ?? '-'}</span>
                <button className="btn btn-secondary btn-sm" type="button" onClick={() => setDraft(fromRecorderCall(call))}>
                  {t('useCall')}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
};
