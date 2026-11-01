import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Download, Play, Plus, Save, Trash2 } from 'lucide-react';
import { api } from '../api/client';
import { useProjectScope } from '../app/ProjectScope';
import {
  ApiAssertion,
  OpenApiOperation,
  fromHarDocument,
  fromOpenApiDocument,
  ApiCaseDraft,
  ApiHeaderRow,
  RecorderApiCall,
  emptyDraft,
  fromRecorderCall,
  newAssertion,
  newHeader,
  slugTestName,
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
  const [operations, setOperations] = useState<OpenApiOperation[]>([]);
  const [importError, setImportError] = useState('');
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [requirements, setRequirements] = useState<{ id: string; title: string }[]>([]);
  const [requirementId, setRequirementId] = useState('');
  const [criteria, setCriteria] = useState<{ id: string; description: string }[]>([]);
  const [criterionIds, setCriterionIds] = useState<string[]>([]);
  const [savedCaseId, setSavedCaseId] = useState<string | null>(null);

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

  useEffect(() => {
    if (!selectedProjectId) return;
    let alive = true;
    void api.getRequirements(selectedProjectId).then((items) => {
      if (alive) setRequirements(items.map((item) => ({ id: item.id, title: item.title })));
    }).catch(() => {});
    return () => {
      alive = false;
    };
  }, [selectedProjectId]);

  useEffect(() => {
    setCriterionIds([]);
    setCriteria([]);
    if (!requirementId) return;
    let alive = true;
    void api.getRequirement(requirementId).then((item) => {
      if (!alive) return;
      const doc = item.qa_model as unknown as { criteria?: { id: string; description: string }[] } | null;
      setCriteria(doc?.criteria ?? []);
    }).catch(() => {});
    return () => {
      alive = false;
    };
  }, [requirementId]);

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

  const readFile = async (file: File | undefined, kind: 'har' | 'openapi') => {
    setImportError('');
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text());
      if (kind === 'har') {
        const imported = fromHarDocument(parsed);
        setCalls(imported);
        setOperations([]);
        if (imported.length === 0) setImportError(t('noCalls'));
      } else {
        const imported = fromOpenApiDocument(parsed);
        setOperations(imported);
        if (imported.length === 0) setImportError(t('noOperations'));
      }
    } catch (reason) {
      setCalls([]);
      setOperations([]);
      setImportError(t('parseFailed', { reason: String(reason) }));
    }
  };

  const applyOperation = (operation: OpenApiOperation) => {
    setDraft({
      ...emptyDraft(slugTestName(operation.summary || `${operation.method}_${operation.path}`)),
      method: operation.method,
      url: operation.path,
      assertions: [{ ...newAssertion('status'), expected: operation.expectedStatus }],
    });
  };

  const save = async () => {
    if (!selectedProjectId || !code || !payload) return;
    setSaving(true);
    setMessage('');
    setSavedCaseId(null);
    try {
      const saved = await api.saveApiCase({
        project_id: selectedProjectId,
        requirement_id: requirementId || null,
        criterion_ids: criterionIds,
        request: payload,
      });
      setMessage(t('saved', { path: saved.file_path }));
      setSavedCaseId(saved.test_case.id);
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
          <div className="api-case-bind-row">
            <label className="flow-editor-field">
              <span>{t('requirement')}</span>
              <select className="form-select" value={requirementId} onChange={(event) => setRequirementId(event.target.value)}>
                <option value="">{t('noRequirement')}</option>
                {requirements.map((item) => (
                  <option key={item.id} value={item.id}>{item.title}</option>
                ))}
              </select>
            </label>
            {criteria.length > 0 && (
              <div className="api-case-criteria">
                <span>{t('criteria')}</span>
                {criteria.map((criterion) => (
                  <label key={criterion.id} className="api-case-criterion">
                    <input
                      type="checkbox"
                      checked={criterionIds.includes(criterion.id)}
                      onChange={() =>
                        setCriterionIds((current) =>
                          current.includes(criterion.id)
                            ? current.filter((id) => id !== criterion.id)
                            : [...current, criterion.id],
                        )
                      }
                    />
                    <span><strong>{criterion.id}</strong> {criterion.description}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
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
              onChange={(event) => {
                const url = event.target.value;
                const autoName = draft.test_name === 'api_case';
                patch({
                  url,
                  ...(autoName && url.trim()
                    ? { test_name: slugTestName(`${draft.method}_${url.replace(/^https?:\/\/[^/]+/, '')}`) }
                    : {}),
                });
              }}
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
          {message && (
            <p className="flow-editor-save-message">
              {message}
              {savedCaseId && (
                <>
                  {' · '}
                  <a href={`/test-cases/${savedCaseId}`}>{t('openCase')}</a>
                </>
              )}
            </p>
          )}
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
        <div className="api-case-file-row">
          <label className="btn btn-secondary btn-sm">
            {t('importHar')}
            <input
              type="file"
              accept="application/json,.har"
              className="api-case-file-input"
              onChange={(event) => void readFile(event.target.files?.[0], 'har')}
            />
          </label>
          <label className="btn btn-secondary btn-sm">
            {t('importOpenapi')}
            <input
              type="file"
              accept="application/json,.yaml,.yml"
              className="api-case-file-input"
              onChange={(event) => void readFile(event.target.files?.[0], 'openapi')}
            />
          </label>
        </div>
        {operations.length > 0 && (
          <ul className="api-case-calls">
            {operations.map((operation) => (
              <li key={`${operation.method} ${operation.path}`}>
                <span className={`api-case-method is-${operation.method.toLowerCase()}`}>{operation.method}</span>
                <code title={operation.summary}>{operation.path}</code>
                <span className="flow-canvas-chip">{operation.expectedStatus}</span>
                <button className="btn btn-secondary btn-sm" type="button" onClick={() => applyOperation(operation)}>
                  {t('useOperation')}
                </button>
              </li>
            ))}
          </ul>
        )}
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
