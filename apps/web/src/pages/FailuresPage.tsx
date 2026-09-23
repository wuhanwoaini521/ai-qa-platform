import React, { useEffect, useState } from 'react';
import { FailureCategory, FailureRecord, LocatorRepairProposal, Project } from '../types';
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
} from 'lucide-react';

interface FailuresPageProps {
  projects: Project[];
  selectedProjectId: string | null;
  onNavigateToRuns?: (runId?: string) => void;
}

export const FailuresPage: React.FC<FailuresPageProps> = ({
  projects,
  selectedProjectId,
  onNavigateToRuns,
}) => {
  const currentProjectId = selectedProjectId || projects[0]?.id || null;

  const [failures, setFailures] = useState<FailureRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedFailure, setSelectedFailure] = useState<FailureRecord | null>(null);

  // Diagnosis & Repair Proposal State
  const [diagnosing, setDiagnosing] = useState<boolean>(false);
  const [diagnosisResult, setDiagnosisResult] = useState<{
    category: string;
    diagnosis: string;
    suggested_action: string;
    confidence: number;
  } | null>(null);

  const [generatingProposal, setGeneratingProposal] = useState<boolean>(false);
  const [repairProposal, setRepairProposal] = useState<LocatorRepairProposal | null>(null);
  const [selectedCandidate, setSelectedCandidate] = useState<string>('');

  const [applyingRepair, setApplyingRepair] = useState<boolean>(false);
  const [repairApplied, setRepairApplied] = useState<boolean>(false);

  const [rerunning, setRerunning] = useState<boolean>(false);
  const [rerunMessage, setRerunMessage] = useState<string | null>(null);

  const fetchFailures = async () => {
    try {
      setLoading(true);
      const data = await api.getFailures(currentProjectId || undefined);
      setFailures(data);
      if (data.length > 0) {
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
    setDiagnosisResult(null);
    setRepairProposal(null);
    setSelectedCandidate('');
    setRepairApplied(f.is_resolved);
    setRerunMessage(null);
  };

  const handleDiagnose = async () => {
    if (!selectedFailure) return;
    try {
      setDiagnosing(true);
      const res = await api.diagnoseFailure(selectedFailure.id);
      setDiagnosisResult(res);
    } catch (err: any) {
      alert(`Diagnosis failed: ${err.message || err}`);
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
      if (proposal.candidates.length > 0) {
        setSelectedCandidate(proposal.candidates[0].locator);
      }
    } catch (err: any) {
      alert(`Failed to generate repair proposal: ${err.message || err}`);
    } finally {
      setGeneratingProposal(false);
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
      // Update resolved state in list
      setFailures((prev) =>
        prev.map((f) => (f.id === selectedFailure.id ? { ...f, is_resolved: true } : f))
      );
      alert(`Successfully patched locator in ${repairProposal.target_file}`);
    } catch (err: any) {
      alert(`Failed to apply repair: ${err.message || err}`);
    } finally {
      setApplyingRepair(false);
    }
  };

  const handleRerunTest = async () => {
    if (!selectedFailure || !currentProjectId || rerunning) return;
    try {
      setRerunning(true);
      setRerunMessage('Triggering verification re-run...');
      const run = await api.createTestRun({
        project_id: currentProjectId,
        target_nodeids: [selectedFailure.nodeid],
        triggered_by: `Re-run verification for failure #${selectedFailure.id.slice(0, 8)}`,
      });
      setRerunMessage(`Re-run dispatched as Run #${run.id.slice(0, 8)} (${run.status})`);
      if (onNavigateToRuns) {
        setTimeout(() => onNavigateToRuns(run.id), 1200);
      }
    } catch (err: any) {
      setRerunMessage(`Re-run error: ${err.message || err}`);
    } finally {
      setRerunning(false);
    }
  };

  const getCategoryBadge = (cat: FailureCategory) => {
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
          <h2 style={{ fontSize: '18px', fontWeight: 700 }}>Failure Intelligence & Locator Self-Healing</h2>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            Automated failure taxonomy classification, root-cause diagnosis, and human-in-the-loop locator healing.
          </p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={fetchFailures}>
          <RefreshCw size={14} /> Refresh Failures
        </button>
      </div>

      {projects.length === 0 ? (
        <div className="card">
          <div className="card-body" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
            Please select or create a project first.
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 2fr', gap: '20px' }}>
          {/* Left: Failures List */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">Recorded Failures ({failures.length})</span>
            </div>
            <div className="card-body" style={{ padding: 0 }}>
              {loading ? (
                <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  Loading failures...
                </div>
              ) : failures.length === 0 ? (
                <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  <CheckCircle2 size={36} style={{ margin: '0 auto 8px', color: '#16a34a' }} />
                  <p style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)' }}>
                    Zero Unresolved Failures
                  </p>
                  <p style={{ fontSize: '12px', marginTop: '4px' }}>
                    All tests are passing or failures have been healed.
                  </p>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  {failures.map((f) => {
                    const isSelected = selectedFailure?.id === f.id;
                    return (
                      <div
                        key={f.id}
                        onClick={() => handleSelectFailure(f)}
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
                            {getCategoryBadge(f.category)}
                            {f.is_resolved && (
                              <span className="badge badge-ready" style={{ fontSize: '10px' }}>
                                ✓ Resolved
                              </span>
                            )}
                          </div>
                          <div style={{ fontSize: '12px', fontWeight: 600, fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#0f172a' }}>
                            {f.nodeid}
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
                      {selectedFailure.nodeid}
                    </span>
                  </div>
                  {getCategoryBadge(selectedFailure.category)}
                </div>
                <div className="card-body">
                  <div style={{ marginBottom: '12px' }}>
                    <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
                      Error Message
                    </div>
                    <div style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '4px', padding: '8px 12px', fontSize: '12px', color: '#991b1b', fontFamily: 'var(--font-mono)' }}>
                      {selectedFailure.error_message}
                    </div>
                  </div>

                  <div>
                    <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
                      Redacted Stack Trace
                    </div>
                    <div style={{ background: '#0f172a', color: '#f8fafc', padding: '10px 12px', borderRadius: '4px', fontSize: '11px', fontFamily: 'var(--font-mono)', maxHeight: '140px', overflowY: 'auto', whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>
                      {selectedFailure.stack_trace || 'No stack trace captured.'}
                    </div>
                  </div>

                  {/* Actions Bar */}
                  <div style={{ display: 'flex', gap: '8px', marginTop: '16px', flexWrap: 'wrap' }}>
                    <button
                      className="btn btn-secondary btn-sm"
                      disabled={diagnosing}
                      onClick={handleDiagnose}
                    >
                      <Zap size={13} color="#2563eb" /> {diagnosing ? 'Diagnosing...' : 'AI Root Cause Diagnosis'}
                    </button>
                    <button
                      className="btn btn-primary btn-sm"
                      disabled={generatingProposal}
                      onClick={handleGenerateProposal}
                    >
                      <Sparkles size={13} /> {generatingProposal ? 'Generating Repair...' : 'Generate Locator Repair Proposal'}
                    </button>
                    <button
                      className="btn btn-secondary btn-sm"
                      disabled={rerunning}
                      onClick={handleRerunTest}
                    >
                      <Play size={13} /> {rerunning ? 'Re-running...' : 'Re-run Test Case'}
                    </button>
                  </div>

                  {rerunMessage && (
                    <div style={{ marginTop: '8px', padding: '8px 12px', background: '#eff6ff', borderRadius: '4px', fontSize: '12px', color: '#1d4ed8' }}>
                      {rerunMessage}
                    </div>
                  )}
                </div>
              </div>

              {/* Diagnosis Result Card */}
              {diagnosisResult && (
                <div className="card" style={{ borderLeft: '4px solid #2563eb' }}>
                  <div className="card-header" style={{ background: '#eff6ff' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Activity size={16} color="#2563eb" />
                      <span className="card-title" style={{ color: '#1d4ed8' }}>
                        AI Root Cause Analysis
                      </span>
                    </div>
                    <span className="badge badge-ready" style={{ fontSize: '11px' }}>
                      Confidence: {(diagnosisResult.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="card-body">
                    <p style={{ fontSize: '13px', color: '#1e293b', lineHeight: 1.6, marginBottom: '10px' }}>
                      {diagnosisResult.diagnosis}
                    </p>
                    <div style={{ background: '#f8fafc', padding: '10px 12px', borderRadius: '4px', border: '1px solid #e2e8f0' }}>
                      <span style={{ fontSize: '11px', fontWeight: 700, color: '#475569', textTransform: 'uppercase' }}>
                        Recommended Next Step:
                      </span>
                      <p style={{ fontSize: '12px', color: '#0f172a', marginTop: '2px' }}>
                        {diagnosisResult.suggested_action}
                      </p>
                    </div>
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
                        Locator Repair Proposal (Confidence: {(repairProposal.confidence * 100).toFixed(0)}%)
                      </span>
                    </div>
                    {repairApplied ? (
                      <span className="badge badge-ready">✓ Repair Applied</span>
                    ) : (
                      <button
                        className="btn btn-primary btn-sm"
                        style={{ background: '#16a34a', borderColor: '#16a34a' }}
                        disabled={applyingRepair}
                        onClick={handleApplyRepair}
                      >
                        <Check size={13} /> {applyingRepair ? 'Applying...' : 'Apply Repair to Code'}
                      </button>
                    )}
                  </div>
                  <div className="card-body">
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
                      <div style={{ background: '#fef2f2', padding: '10px', borderRadius: '4px', border: '1px solid #fee2e2' }}>
                        <div style={{ fontSize: '11px', color: '#991b1b', fontWeight: 700 }}>Broken Locator</div>
                        <code style={{ fontSize: '12px', color: '#b91c1c', wordBreak: 'break-all' }}>
                          {repairProposal.broken_locator}
                        </code>
                      </div>
                      <div style={{ background: '#f0fdf4', padding: '10px', borderRadius: '4px', border: '1px solid #dcfce7' }}>
                        <div style={{ fontSize: '11px', color: '#166534', fontWeight: 700 }}>Proposed Replacement</div>
                        <code style={{ fontSize: '12px', color: '#15803d', wordBreak: 'break-all' }}>
                          {selectedCandidate || repairProposal.proposed_locator}
                        </code>
                      </div>
                    </div>

                    {/* Candidate Ranking */}
                    {repairProposal.candidates.length > 1 && (
                      <div style={{ marginBottom: '14px' }}>
                        <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
                          Candidate Ranking ({repairProposal.candidates.length} options)
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                          {repairProposal.candidates.map((cand, idx) => (
                            <label
                              key={idx}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '8px',
                                padding: '6px 10px',
                                background: selectedCandidate === cand.locator ? '#eff6ff' : '#f8fafc',
                                border: selectedCandidate === cand.locator ? '1px solid #3b82f6' : '1px solid #e2e8f0',
                                borderRadius: '4px',
                                cursor: 'pointer',
                                fontSize: '12px',
                              }}
                            >
                              <input
                                type="radio"
                                name="candidate_locator"
                                checked={selectedCandidate === cand.locator}
                                onChange={() => setSelectedCandidate(cand.locator)}
                              />
                              <div style={{ flex: 1, display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{cand.locator}</span>
                                <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>
                                  {cand.strategy} ({(cand.confidence * 100).toFixed(0)}%)
                                </span>
                              </div>
                            </label>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Diff Preview */}
                    <div>
                      <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
                        Code Diff Preview ({repairProposal.target_file}:{repairProposal.line_number})
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
                        {repairProposal.diff_preview}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="card">
              <div className="card-body" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
                Select a test failure to perform AI root-cause diagnosis or generate locator repair proposals.
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
