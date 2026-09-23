import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AIFailureDiagnosisResponse,
  FailureCategory,
  FailureRecurrenceItem,
  FailureRecord,
  JiraBugDraft,
  JiraCreateBugResponse,
  LocatorRepairProposal,
  LocatorSemanticReviewResponse,
  Project,
} from '../types';
import { api } from '../api/client';
import {
  AlertTriangle,
  Sparkles,
  RefreshCw,
  CheckCircle2,
  ChevronRight,
  Play,
  Check,
  Activity,
  Zap,
  ShieldCheck,
  History,
  Bug,
  Code2,
  ExternalLink,
} from 'lucide-react';

interface FailuresPageProps {
  projects: Project[];
  selectedProjectId: string | null;
  /** Deep-link target: when set, this failure is selected once the list resolves. */
  initialFailureId?: string | null;
  /** Lets the router shell mirror row selection into the URL. */
  onSelectFailure?: (failureId: string) => void;
  /** Opens the failing test file in the Automation Studio. */
  onOpenInStudio?: (filePath: string) => void;
  onNavigateToRuns?: (runId?: string) => void;
}

export const FailuresPage: React.FC<FailuresPageProps> = ({
  projects,
  selectedProjectId,
  initialFailureId,
  onSelectFailure,
  onOpenInStudio,
  onNavigateToRuns,
}) => {
  const { t } = useTranslation('failures');
  const currentProjectId = selectedProjectId || projects[0]?.id || null;

  const [failures, setFailures] = useState<FailureRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedFailure, setSelectedFailure] = useState<FailureRecord | null>(null);

  // Diagnosis State
  const [diagnosing, setDiagnosing] = useState<boolean>(false);
  const [aiDiagnosis, setAiDiagnosis] = useState<AIFailureDiagnosisResponse | null>(null);

  // Locator Repair Proposal State
  const [generatingProposal, setGeneratingProposal] = useState<boolean>(false);
  const [repairProposal, setRepairProposal] = useState<LocatorRepairProposal | null>(null);
  const [selectedCandidate, setSelectedCandidate] = useState<string>('');

  // Semantic Review State
  const [reviewingSemantic, setReviewingSemantic] = useState<boolean>(false);
  const [semanticReview, setSemanticReview] = useState<LocatorSemanticReviewResponse | null>(null);

  // Recurrence State
  const [recurrenceList, setRecurrenceList] = useState<FailureRecurrenceItem[]>([]);
  const [loadingRecurrence, setLoadingRecurrence] = useState<boolean>(false);

  // Jira Bug Ticket State (Phase 9)
  const [isJiraBugModalOpen, setIsJiraBugModalOpen] = useState<boolean>(false);
  const [jiraBugDraft, setJiraBugDraft] = useState<JiraBugDraft | null>(null);
  const [generatingJiraDraft, setGeneratingJiraDraft] = useState<boolean>(false);
  const [creatingJiraBug, setCreatingJiraBug] = useState<boolean>(false);
  const [jiraBugResult, setJiraBugResult] = useState<JiraCreateBugResponse | null>(null);

  const [applyingRepair, setApplyingRepair] = useState<boolean>(false);
  const [repairApplied, setRepairApplied] = useState<boolean>(false);
  // Failures repaired in this session. The API records the patch on the workspace, not on the
  // failure row, so "resolved" is deliberately a local view state rather than a fabricated field.
  const [resolvedFailureIds, setResolvedFailureIds] = useState<string[]>([]);

  const [rerunning, setRerunning] = useState<boolean>(false);
  const [rerunMessage, setRerunMessage] = useState<string | null>(null);

  const fetchFailures = async () => {
    try {
      setLoading(true);
      const data = await api.getFailures(currentProjectId || undefined);
      setFailures(data);
      const deepLinked = initialFailureId ? data.find((f) => f.id === initialFailureId) : undefined;
      if (deepLinked) {
        handleSelectFailure(deepLinked);
      } else if (data.length > 0) {
        handleSelectFailure(data[0]);
      } else {
        setSelectedFailure(null);
      }
    } catch (err) {
      console.error('Failed to load failures', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFailures();
  }, [currentProjectId]);

  const handleSelectFailure = (f: FailureRecord) => {
    setSelectedFailure(f);
    setAiDiagnosis(null);
    setRepairProposal(null);
    setSelectedCandidate('');
    setSemanticReview(null);
    setRepairApplied(false);
    setRerunMessage(null);
    fetchRecurrence(f.id);
  };

  const fetchRecurrence = async (failureId: string) => {
    try {
      setLoadingRecurrence(true);
      const list = await api.getFailureRecurrence(failureId);
      setRecurrenceList(list);
    } catch (err) {
      console.error('Failed to fetch recurrence', err);
      setRecurrenceList([]);
    } finally {
      setLoadingRecurrence(false);
    }
  };

  const handleDiagnoseAI = async () => {
    if (!selectedFailure) return;
    try {
      setDiagnosing(true);
      const res = await api.diagnoseFailureAI(selectedFailure.id);
      setAiDiagnosis(res);
    } catch (err: any) {
      alert(t('alertDiagnoseFailed', { error: err.message || err }));
    } finally {
      setDiagnosing(false);
    }
  };

  const handleGenerateProposal = async () => {
    if (!selectedFailure) return;
    try {
      setGeneratingProposal(true);
      const proposal = await api.generateRepairProposal(selectedFailure.id);
      setRepairProposal(proposal);
      setSemanticReview(null);
      if (proposal.proposed_locator) {
        setSelectedCandidate(proposal.proposed_locator);
      }
    } catch (err: any) {
      alert(t('alertProposalFailed', { error: err.message || err }));
    } finally {
      setGeneratingProposal(false);
    }
  };

  const handleSemanticReview = async () => {
    if (!selectedFailure || !repairProposal) return;
    const chosenLocator = selectedCandidate || repairProposal.proposed_locator;
    try {
      setReviewingSemantic(true);
      const review = await api.getSemanticLocatorReview(
        selectedFailure.id,
        repairProposal.old_locator,
        chosenLocator
      );
      setSemanticReview(review);
    } catch (err: any) {
      alert(t('alertSemanticReviewFailed', { error: err.message || err }));
    } finally {
      setReviewingSemantic(false);
    }
  };

  const handleApplyRepair = async () => {
    if (!selectedFailure || !repairProposal) return;
    const chosenLocator = selectedCandidate || repairProposal.proposed_locator;
    try {
      setApplyingRepair(true);
      await api.applyRepair(selectedFailure.id, {
        target_file: repairProposal.target_file,
        old_locator: repairProposal.broken_locator,
        new_locator: chosenLocator,
      });
      setRepairApplied(true);
      setResolvedFailureIds((prev) =>
        prev.includes(selectedFailure.id) ? prev : [...prev, selectedFailure.id]
      );
      alert(t('alertRepairApplied', { file: repairProposal.target_file }));
    } catch (err: any) {
      alert(t('alertApplyRepairFailed', { error: err.message || err }));
    } finally {
      setApplyingRepair(false);
    }
  };

  const handleRerunTest = async () => {
    if (!selectedFailure || !currentProjectId || rerunning) return;
    try {
      setRerunning(true);
      setRerunMessage(t('rerunTriggering'));
      const target = selectedFailure.test_nodeid;
      const run = await api.createTestRun({
        project_id: currentProjectId,
        workspace_id: currentProjectId,
        nodeids: [target],
        requested_by: `Re-run verification for failure #${selectedFailure.id.slice(0, 8)}`,
      });
      setRerunMessage(
        t('rerunDispatched', { runId: run.id.slice(0, 8), status: run.status })
      );
      if (onNavigateToRuns) {
        setTimeout(() => onNavigateToRuns(run.id), 1200);
      }
    } catch (err: any) {
      setRerunMessage(t('rerunError', { error: err.message || err }));
    } finally {
      setRerunning(false);
    }
  };

  const handleOpenJiraBugModal = async () => {
    if (!selectedFailure) return;
    setIsJiraBugModalOpen(true);
    setGeneratingJiraDraft(true);
    setJiraBugResult(null);
    try {
      const draft = await api.generateJiraBugDraft({
        failure_id: selectedFailure.id,
        project_key: 'QA',
        issue_type: 'Bug',
      });
      setJiraBugDraft(draft);
    } catch (err) {
      console.error('Failed to generate Jira bug draft', err);
    } finally {
      setGeneratingJiraDraft(false);
    }
  };

  const handleConfirmCreateJiraBug = async (confirmPublish: boolean) => {
    if (!jiraBugDraft) return;
    setCreatingJiraBug(true);
    try {
      const res = await api.createJiraBug({
        draft: jiraBugDraft,
        confirm_publish: confirmPublish,
      });
      setJiraBugResult(res);
    } catch (err) {
      console.error('Failed to create Jira bug', err);
    } finally {
      setCreatingJiraBug(false);
    }
  };

  const getCategoryBadge = (cat?: FailureCategory | string) => {
    switch (cat) {
      case 'LOCATOR_CHANGED':
        return (
          <span className="badge badge-draft" style={{ background: '#f3e8ff', color: '#7e22ce' }}>
            LOCATOR_CHANGED
          </span>
        );
      case 'TIMING_ISSUE':
        return (
          <span className="badge badge-draft" style={{ background: '#fef3c7', color: '#b45309' }}>
            TIMING_ISSUE
          </span>
        );
      case 'ASSERTION_FAILURE':
        return (
          <span className="badge badge-draft" style={{ background: '#fee2e2', color: '#b91c1c' }}>
            ASSERTION_FAILURE
          </span>
        );
      case 'ENVIRONMENT_ERROR':
        return (
          <span className="badge badge-draft" style={{ background: '#f1f5f9', color: '#475569' }}>
            ENVIRONMENT_ERROR
          </span>
        );
      default:
        return <span className="badge badge-draft">{cat}</span>;
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
        <div>
          <h2 style={{ fontSize: '18px', fontWeight: 700 }}>{t('title')}</h2>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            {t('subtitle')}
          </p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={fetchFailures}>
          <RefreshCw size={14} /> {t('refresh')}
        </button>
      </div>

      {projects.length === 0 ? (
        <div className="card">
          <div className="card-body" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
            {t('noProject')}
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 2fr', gap: '20px' }}>
          {/* Left: Failures List */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">
                {t('recordedCount', { count: failures.length })}
              </span>
            </div>
            <div className="card-body" style={{ padding: 0 }}>
              {loading ? (
                <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  {t('loading')}
                </div>
              ) : failures.length === 0 ? (
                <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  <CheckCircle2 size={36} style={{ margin: '0 auto 8px', color: '#16a34a' }} />
                  <p style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)' }}>
                    {t('emptyTitle')}
                  </p>
                  <p style={{ fontSize: '12px', marginTop: '4px' }}>
                    {t('emptyBody')}
                  </p>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  {failures.map((f) => {
                    const isSelected = selectedFailure?.id === f.id;
                    return (
                      <div
                        key={f.id}
                        onClick={() => {
                          handleSelectFailure(f);
                          if (onSelectFailure) onSelectFailure(f.id);
                        }}
                        style={{
                          padding: '12px 16px',
                          borderBottom: '1px solid var(--border-color)',
                          cursor: 'pointer',
                          backgroundColor: isSelected ? '#eff6ff' : 'transparent',
                          borderLeft: isSelected ? '3px solid var(--primary)' : '3px solid transparent',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                        }}
                      >
                        <div style={{ minWidth: 0, flex: 1, paddingRight: '8px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                            {getCategoryBadge(f.classification)}
                            {resolvedFailureIds.includes(f.id) && (
                              <span className="badge badge-ready" style={{ fontSize: '10px' }}>
                                {t('resolved')}
                              </span>
                            )}
                          </div>
                          <div style={{ fontSize: '12px', fontWeight: 600, fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#0f172a' }}>
                            {f.test_nodeid}
                          </div>
                          <div style={{ fontSize: '11px', color: '#dc2626', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: '2px' }}>
                            {f.error_message}
                          </div>
                        </div>
                        <ChevronRight size={16} color={isSelected ? '#2563eb' : '#94a3b8'} />
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Right: Selected Failure Diagnosis & Repair Workbench */}
          {selectedFailure ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* Error Details Card */}
              <div className="card">
                <div className="card-header">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <AlertTriangle size={16} color="#dc2626" />
                    <span className="card-title" style={{ fontFamily: 'var(--font-mono)', fontSize: '13px' }}>
                      {selectedFailure.test_nodeid}
                    </span>
                  </div>
                  {getCategoryBadge(selectedFailure.classification)}
                </div>
                <div className="card-body">
                  <div style={{ marginBottom: '12px' }}>
                    <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
                      {t('errorMessage')}
                    </div>
                    <div style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '4px', padding: '8px 12px', fontSize: '12px', color: '#991b1b', fontFamily: 'var(--font-mono)' }}>
                      {selectedFailure.error_message}
                    </div>
                  </div>

                  <div>
                    <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
                      {t('stackTrace')}
                    </div>
                    <div style={{ background: '#0f172a', color: '#f8fafc', padding: '10px 12px', borderRadius: '4px', fontSize: '11px', fontFamily: 'var(--font-mono)', maxHeight: '140px', overflowY: 'auto', whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>
                      {selectedFailure.stack_trace || t('noStackTrace')}
                    </div>
                  </div>

                  {/* Actions Bar */}
                  <div style={{ display: 'flex', gap: '8px', marginTop: '16px', flexWrap: 'wrap' }}>
                    <button
                      className="btn btn-secondary btn-sm"
                      disabled={diagnosing}
                      onClick={handleDiagnoseAI}
                    >
                      <Zap size={13} color="#2563eb" />{' '}
                      {diagnosing ? t('diagnosing') : t('diagnoseAI')}
                    </button>
                    <button
                      className="btn btn-primary btn-sm"
                      disabled={generatingProposal}
                      onClick={handleGenerateProposal}
                    >
                      <Sparkles size={13} />{' '}
                      {generatingProposal ? t('generatingProposal') : t('generateProposal')}
                    </button>
                    <button
                      className="btn btn-secondary btn-sm"
                      disabled={rerunning}
                      onClick={handleRerunTest}
                    >
                      <Play size={13} /> {rerunning ? t('rerunning') : t('rerun')}
                    </button>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={handleOpenJiraBugModal}
                      title={t('jiraDraftTitle')}
                    >
                      <Bug size={13} color="#e11d48" /> {t('createJiraDraft')}
                    </button>
                    {onOpenInStudio && (
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => onOpenInStudio(selectedFailure.test_nodeid.split('::')[0])}
                        title={t('openInStudioTitle')}
                      >
                        <Code2 size={13} /> {t('openInStudio')}
                      </button>
                    )}
                  </div>

                  {rerunMessage && (
                    <div style={{ marginTop: '8px', padding: '8px 12px', background: '#eff6ff', borderRadius: '4px', fontSize: '12px', color: '#1d4ed8' }}>
                      {rerunMessage}
                    </div>
                  )}
                </div>
              </div>

              {/* AI Diagnosis Result Card (Evidence vs Hypotheses) */}
              {aiDiagnosis && (
                <div className="card" style={{ borderLeft: '4px solid #2563eb' }}>
                  <div className="card-header" style={{ background: '#eff6ff' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Activity size={16} color="#2563eb" />
                      <span className="card-title" style={{ color: '#1d4ed8' }}>
                        {t('diagnosisTitle', { classification: aiDiagnosis.classification })}
                      </span>
                    </div>
                    <span className="badge badge-ready" style={{ fontSize: '11px' }}>
                      {t('confidence', { value: (aiDiagnosis.confidence * 100).toFixed(0) })}
                    </span>
                  </div>
                  <div className="card-body">
                    <p style={{ fontSize: '13px', color: '#1e293b', lineHeight: 1.6, marginBottom: '12px' }}>
                      <b>{t('rootCause')}</b> {aiDiagnosis.root_cause}
                    </p>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
                      {/* Evidence */}
                      <div style={{ background: '#f8fafc', padding: '10px 12px', borderRadius: '4px', border: '1px solid #e2e8f0' }}>
                        <span style={{ fontSize: '11px', fontWeight: 700, color: '#475569', textTransform: 'uppercase' }}>
                          {t('evidence')}
                        </span>
                        <ul style={{ margin: '4px 0 0 16px', padding: 0, fontSize: '12px', color: '#0f172a' }}>
                          {aiDiagnosis.evidence.map((ev, i) => (
                            <li key={i}>{ev}</li>
                          ))}
                        </ul>
                      </div>

                      {/* Hypotheses */}
                      <div style={{ background: '#f8fafc', padding: '10px 12px', borderRadius: '4px', border: '1px solid #e2e8f0' }}>
                        <span style={{ fontSize: '11px', fontWeight: 700, color: '#475569', textTransform: 'uppercase' }}>
                          {t('hypotheses')}
                        </span>
                        <ul style={{ margin: '4px 0 0 16px', padding: 0, fontSize: '12px', color: '#0f172a' }}>
                          {aiDiagnosis.hypotheses.map((hyp, i) => (
                            <li key={i}>{hyp}</li>
                          ))}
                        </ul>
                      </div>
                    </div>

                    {/* Recommended Actions */}
                    {aiDiagnosis.recommended_actions.length > 0 && (
                      <div style={{ background: '#f0fdf4', padding: '10px 12px', borderRadius: '4px', border: '1px solid #bbf7d0' }}>
                        <span style={{ fontSize: '11px', fontWeight: 700, color: '#166534', textTransform: 'uppercase' }}>
                          {t('recommended')}
                        </span>
                        <ul style={{ margin: '4px 0 0 16px', padding: 0, fontSize: '12px', color: '#14532d' }}>
                          {aiDiagnosis.recommended_actions.map((act, i) => (
                            <li key={i}>{act}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Locator Repair Proposal Card */}
              {repairProposal && (
                <div className="card" style={{ borderLeft: '4px solid #16a34a' }}>
                  <div className="card-header" style={{ background: '#f0fdf4' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Sparkles size={16} color="#16a34a" />
                      <span className="card-title" style={{ color: '#166534' }}>
                        {t('proposalTitle', {
                          value: (repairProposal.confidence * 100).toFixed(0),
                        })}
                      </span>
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        className="btn btn-secondary btn-sm"
                        disabled={reviewingSemantic}
                        onClick={handleSemanticReview}
                      >
                        <ShieldCheck size={13} color="#2563eb" />{' '}
                        {reviewingSemantic ? t('reviewing') : t('semanticReview')}
                      </button>
                      {repairApplied ? (
                        <span className="badge badge-ready">{t('repairApplied')}</span>
                      ) : (
                        <button
                          className="btn btn-primary btn-sm"
                          style={{ background: '#16a34a', borderColor: '#16a34a' }}
                          disabled={applyingRepair}
                          onClick={handleApplyRepair}
                        >
                          <Check size={13} /> {applyingRepair ? t('applying') : t('applyRepair')}
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="card-body">
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
                      <div style={{ background: '#fef2f2', padding: '10px', borderRadius: '4px', border: '1px solid #fee2e2' }}>
                        <div style={{ fontSize: '11px', color: '#991b1b', fontWeight: 700 }}>{t('brokenLocator')}</div>
                        <code style={{ fontSize: '12px', color: '#b91c1c', wordBreak: 'break-all' }}>
                          {repairProposal.old_locator || repairProposal.broken_locator}
                        </code>
                      </div>
                      <div style={{ background: '#f0fdf4', padding: '10px', borderRadius: '4px', border: '1px solid #dcfce7' }}>
                        <div style={{ fontSize: '11px', color: '#166534', fontWeight: 700 }}>
                          {t('proposedReplacement', { strategy: repairProposal.strategy })}
                        </div>
                        <code style={{ fontSize: '12px', color: '#15803d', wordBreak: 'break-all' }}>
                          {selectedCandidate || repairProposal.proposed_locator}
                        </code>
                      </div>
                    </div>

                    {/* Semantic Review Results Banner */}
                    {semanticReview && (
                      <div
                        style={{
                          marginBottom: '12px',
                          padding: '10px 12px',
                          borderRadius: '4px',
                          background: semanticReview.is_semantically_equivalent ? '#f0fdf4' : '#fffbeb',
                          border: `1px solid ${semanticReview.is_semantically_equivalent ? '#bbf7d0' : '#fde68a'}`,
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                          <span style={{ fontSize: '12px', fontWeight: 700, color: semanticReview.is_semantically_equivalent ? '#166534' : '#92400e' }}>
                            {semanticReview.is_semantically_equivalent
                              ? t('semanticallyEquivalent')
                              : t('nonEquivalent')}
                          </span>
                          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                            {t('reviewConfidence', {
                              value: (semanticReview.confidence * 100).toFixed(0),
                            })}
                          </span>
                        </div>
                        <p style={{ fontSize: '12px', color: '#334155', margin: 0 }}>
                          {semanticReview.explanation}
                        </p>
                        {semanticReview.risk_warning && (
                          <p style={{ fontSize: '11px', color: '#dc2626', margin: '4px 0 0 0', fontWeight: 600 }}>
                            {t('riskWarning', { warning: semanticReview.risk_warning })}
                          </p>
                        )}
                      </div>
                    )}

                    {/* Diff Preview */}
                    <div>
                      <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
                        {t('diffPreview', {
                          file: repairProposal.file_path || repairProposal.target_file,
                        })}
                      </div>
                      <div
                        style={{
                          background: '#0f172a',
                          color: '#f8fafc',
                          padding: '10px 12px',
                          borderRadius: '4px',
                          fontSize: '11px',
                          fontFamily: 'var(--font-mono)',
                          whiteSpace: 'pre-wrap',
                          lineHeight: 1.5,
                        }}
                      >
                        {repairProposal.code_diff || repairProposal.diff_preview}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Similar Past Failures / Recurrence History */}
              <div className="card">
                <div className="card-header">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <History size={15} color="#64748b" />
                    <span className="card-title">
                      {t('recurrenceTitle', { count: recurrenceList.length })}
                    </span>
                  </div>
                </div>
                <div className="card-body" style={{ padding: 0 }}>
                  {loadingRecurrence ? (
                    <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
                      {t('recurrenceLoading')}
                    </div>
                  ) : recurrenceList.length === 0 ? (
                    <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
                      {t('recurrenceEmpty')}
                    </div>
                  ) : (
                    <table className="data-table" style={{ fontSize: '11px' }}>
                      <thead>
                        <tr>
                          <th style={{ padding: '6px 8px' }}>{t('category')}</th>
                          <th style={{ padding: '6px 8px' }}>{t('runId')}</th>
                          <th style={{ padding: '6px 8px' }}>{t('recordedAt')}</th>
                          <th style={{ padding: '6px 8px' }}>{t('errorDetails')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {recurrenceList.map((rec) => (
                          <tr key={rec.failure_id}>
                            <td style={{ padding: '6px 8px' }}>
                              <span className="badge badge-draft" style={{ fontSize: '10px' }}>
                                {rec.classification}
                              </span>
                            </td>
                            <td style={{ padding: '6px 8px', fontFamily: 'var(--font-mono)' }}>
                              #{rec.run_id.slice(0, 8)}
                            </td>
                            <td style={{ padding: '6px 8px', color: 'var(--text-muted)' }}>
                              {new Date(rec.created_at).toLocaleDateString()}
                            </td>
                            <td style={{ padding: '6px 8px', color: '#dc2626' }}>
                              {rec.error_message ? rec.error_message.slice(0, 70) + '...' : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="card">
              <div className="card-body" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
                {t('selectPrompt')}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Jira Bug Ticket Creation Modal (Phase 9) */}
      {isJiraBugModalOpen && (
        <div className="modal-backdrop">
          <div className="modal" style={{ maxWidth: '750px', width: '90%' }}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Bug size={18} color="#e11d48" />
                <h3 className="modal-title">{t('jiraModalTitle')}</h3>
              </div>
              <button
                className="btn btn-icon"
                onClick={() => setIsJiraBugModalOpen(false)}
                style={{ padding: '4px' }}
              >
                ✕
              </button>
            </div>

            <div className="modal-body">
              {generatingJiraDraft ? (
                <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  <Sparkles size={24} className="spin" style={{ margin: '0 auto 12px', color: '#e11d48' }} />
                  <p>{t('jiraSynthesizing')}</p>
                </div>
              ) : jiraBugDraft ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  {jiraBugResult && (
                    <div
                      style={{
                        padding: '12px 16px',
                        borderRadius: '6px',
                        backgroundColor: jiraBugResult.published ? '#f0fdf4' : '#eff6ff',
                        border: `1px solid ${jiraBugResult.published ? '#86efac' : '#93c5fd'}`,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 600, fontSize: '13px', color: jiraBugResult.published ? '#166534' : '#1e40af' }}>
                          {jiraBugResult.message}
                        </div>
                        {jiraBugResult.url && (
                          <a
                            href={jiraBugResult.url}
                            target="_blank"
                            rel="noreferrer"
                            style={{ fontSize: '12px', color: '#2563eb', display: 'inline-flex', alignItems: 'center', gap: '4px', marginTop: '4px' }}
                          >
                            {t('openJiraIssue', { key: jiraBugResult.key })} <ExternalLink size={12} />
                          </a>
                        )}
                      </div>
                      <span className="badge badge-draft" style={{ fontSize: '11px' }}>
                        {jiraBugResult.status}
                      </span>
                    </div>
                  )}

                  <div className="form-group">
                    <label className="form-label">{t('issueSummary')}</label>
                    <input
                      type="text"
                      className="form-input"
                      value={jiraBugDraft.summary}
                      onChange={(e) => setJiraBugDraft({ ...jiraBugDraft, summary: e.target.value })}
                    />
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px' }}>
                    <div className="form-group">
                      <label className="form-label">{t('projectKey')}</label>
                      <input
                        type="text"
                        className="form-input"
                        value={jiraBugDraft.project_key}
                        onChange={(e) => setJiraBugDraft({ ...jiraBugDraft, project_key: e.target.value })}
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">{t('issueType')}</label>
                      <input
                        type="text"
                        className="form-input"
                        value={jiraBugDraft.issue_type}
                        onChange={(e) => setJiraBugDraft({ ...jiraBugDraft, issue_type: e.target.value })}
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">{t('common:priority')}</label>
                      <select
                        className="form-select"
                        value={jiraBugDraft.priority}
                        onChange={(e) => setJiraBugDraft({ ...jiraBugDraft, priority: e.target.value })}
                      >
                        <option value="Critical">{t('priorityCritical')}</option>
                        <option value="High">{t('priorityHigh')}</option>
                        <option value="Medium">{t('priorityMedium')}</option>
                        <option value="Low">{t('priorityLow')}</option>
                      </select>
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">{t('descriptionDiagnostics')}</label>
                    <textarea
                      rows={5}
                      className="form-textarea"
                      value={jiraBugDraft.description}
                      onChange={(e) => setJiraBugDraft({ ...jiraBugDraft, description: e.target.value })}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">{t('reproductionSteps')}</label>
                    <div style={{ background: '#f8fafc', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '10px 12px' }}>
                      <ol style={{ paddingLeft: '18px', margin: 0, fontSize: '12px', color: '#334155' }}>
                        {jiraBugDraft.steps_to_reproduce.map((st, i) => (
                          <li key={i}>{st}</li>
                        ))}
                      </ol>
                    </div>
                  </div>
                </div>
              ) : (
                <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  {t('jiraDraftFailed')}
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setIsJiraBugModalOpen(false)}
              >
                {t('common:close')}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={!jiraBugDraft || creatingJiraBug}
                onClick={() => handleConfirmCreateJiraBug(false)}
              >
                {t('validateDryRun')}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={!jiraBugDraft || creatingJiraBug}
                onClick={() => handleConfirmCreateJiraBug(true)}
              >
                {creatingJiraBug ? t('creatingTicket') : t('createTicket')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
