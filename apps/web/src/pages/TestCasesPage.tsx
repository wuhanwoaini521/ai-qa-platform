import React, { useEffect, useState } from 'react';
import {
  AutomationBinding,
  AutomationStatus,
  GenerateAutomationResponse,
  Project,
  TestCase,
  TestCaseCreate,
  TestCasePriority,
} from '../types';
import { api } from '../api/client';
import {
  Plus,
  CheckSquare,
  Tag,
  ChevronRight,
  Code2,
  Sparkles,
  Play,
  ExternalLink,
  Edit3,
  CheckCircle,
} from 'lucide-react';

interface TestCasesPageProps {
  projects: Project[];
  selectedProjectId: string | null;
  onNavigateToStudio?: (filePath: string) => void;
  onNavigateToRuns?: (runId?: string) => void;
}

export const TestCasesPage: React.FC<TestCasesPageProps> = ({
  projects,
  selectedProjectId,
  onNavigateToStudio,
  onNavigateToRuns,
}) => {
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCase, setSelectedCase] = useState<TestCase | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Automation Binding & Generation State
  const [selectedBinding, setSelectedBinding] = useState<AutomationBinding | null>(null);
  const [isBindingModalOpen, setIsBindingModalOpen] = useState(false);
  const [bindingFormData, setBindingFormData] = useState<{
    test_file_path: string;
    test_node_id: string;
    status: AutomationStatus;
  }>({
    test_file_path: '',
    test_node_id: '',
    status: 'MANUAL',
  });

  const [generatedDraft, setGeneratedDraft] = useState<GenerateAutomationResponse | null>(null);
  const [generating, setGenerating] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [runningCase, setRunningCase] = useState(false);
  const [runMessage, setRunMessage] = useState<string | null>(null);

  // Quality Intelligence & History State
  const [caseHistory, setCaseHistory] = useState<any | null>(null);
  const [loadingCaseHistory, setLoadingCaseHistory] = useState(false);

  // Form State
  const [formData, setFormData] = useState<TestCaseCreate>({
    project_id: selectedProjectId || (projects[0]?.id ?? ''),
    title: '',
    preconditions: '',
    steps: [],
    expected_result: '',
    priority: 'P1',
    automation_status: 'MANUAL',
    tags: [],
  });
  const [stepsText, setStepsText] = useState('');
  const [tagsText, setTagsText] = useState('');

  const fetchTestCases = async () => {
    try {
      setLoading(true);
      const data = await api.getTestCases(selectedProjectId || undefined);
      setTestCases(data);
      if (data.length > 0) {
        const found = selectedCase ? data.find((c) => c.id === selectedCase.id) || data[0] : data[0];
        setSelectedCase(found);
        fetchBinding(found.id);
      } else {
        setSelectedCase(null);
        setSelectedBinding(null);
      }
    } catch (err) {
      console.error('Failed to load test cases', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchBinding = async (caseId: string) => {
    try {
      const binding = await api.getAutomationBinding(caseId);
      setSelectedBinding(binding);
      if (binding) {
        setBindingFormData({
          test_file_path: binding.test_file_path,
          test_node_id: binding.test_node_id,
          status: binding.status,
        });
        if (binding.test_node_id && selectedProjectId) {
          fetchCaseHistory(binding.test_node_id, selectedProjectId);
        } else {
          setCaseHistory(null);
        }
      } else {
        setBindingFormData({
          test_file_path: `tests/test_${caseId.slice(0, 8)}.py`,
          test_node_id: `tests/test_${caseId.slice(0, 8)}.py::test_${caseId.slice(0, 8)}`,
          status: 'MANUAL',
        });
        setCaseHistory(null);
      }
    } catch (err) {
      console.error('Failed to fetch binding', err);
    }
  };

  const fetchCaseHistory = async (nodeid: string, projectId: string) => {
    try {
      setLoadingCaseHistory(true);
      const hist = await api.getTestHistory(nodeid, projectId, 20);
      setCaseHistory(hist);
    } catch (err) {
      console.error('Failed to fetch case history', err);
      setCaseHistory(null);
    } finally {
      setLoadingCaseHistory(false);
    }
  };

  useEffect(() => {
    fetchTestCases();
  }, [selectedProjectId]);

  const handleSelectCase = (tc: TestCase) => {
    setSelectedCase(tc);
    setGeneratedDraft(null);
    setRunMessage(null);
    fetchBinding(tc.id);
  };

  const handleCreateTestCase = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.title.trim()) return;

    const parsedSteps = stepsText
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);
    const parsedTags = tagsText
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    try {
      const created = await api.createTestCase({
        ...formData,
        project_id: selectedProjectId || formData.project_id || projects[0]?.id || '',
        steps: parsedSteps,
        tags: parsedTags,
      });
      setTestCases([created, ...testCases]);
      setSelectedCase(created);
      setIsModalOpen(false);
      setFormData({
        project_id: selectedProjectId || (projects[0]?.id ?? ''),
        title: '',
        preconditions: '',
        steps: [],
        expected_result: '',
        priority: 'P1',
        automation_status: 'MANUAL',
        tags: [],
      });
      setStepsText('');
      setTagsText('');
      fetchBinding(created.id);
    } catch (err) {
      console.error('Failed to create test case', err);
    }
  };

  const handleUpdateStatus = async (caseId: string, automationStatus: AutomationStatus) => {
    try {
      const updated = await api.updateTestCase(caseId, { automation_status: automationStatus });
      setTestCases(testCases.map((tc) => (tc.id === caseId ? updated : tc)));
      if (selectedCase?.id === caseId) {
        setSelectedCase(updated);
      }
    } catch (err) {
      console.error('Failed to update automation status', err);
    }
  };

  const handleGenerateAutomation = async () => {
    if (!selectedCase) return;
    try {
      setGenerating(true);
      const draft = await api.generateAutomation(selectedCase.id, true);
      setGeneratedDraft(draft);
    } catch (err: any) {
      alert(`Generation error: ${err.message || err}`);
    } finally {
      setGenerating(false);
    }
  };

  const handleSaveDraftToWorkspace = async () => {
    if (!selectedCase || !generatedDraft || !selectedProjectId) return;
    try {
      setSavingDraft(true);
      // Write file into workspace
      await api.writeWorkspaceFile(
        selectedProjectId,
        generatedDraft.target_file,
        generatedDraft.suggested_code
      );
      // Bind to test case
      const nodeid = `${generatedDraft.target_file}::test_${selectedCase.title
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '_')
        .replace(/(^_|_$)/g, '')}`;

      const savedBinding = await api.saveAutomationBinding(selectedCase.id, {
        test_file_path: generatedDraft.target_file,
        test_node_id: nodeid,
        status: 'AUTOMATED',
        last_generated_code: generatedDraft.suggested_code,
      });

      setSelectedBinding(savedBinding);
      await handleUpdateStatus(selectedCase.id, 'AUTOMATED');
      alert(`Automation scaffold saved to ${generatedDraft.target_file} and bound to test case.`);
    } catch (err: any) {
      alert(`Failed to save draft to workspace: ${err.message || err}`);
    } finally {
      setSavingDraft(false);
    }
  };

  const handleSaveManualBinding = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCase) return;
    try {
      const saved = await api.saveAutomationBinding(selectedCase.id, {
        test_file_path: bindingFormData.test_file_path,
        test_node_id: bindingFormData.test_node_id,
        status: bindingFormData.status,
      });
      setSelectedBinding(saved);
      await handleUpdateStatus(selectedCase.id, bindingFormData.status);
      setIsBindingModalOpen(false);
    } catch (err: any) {
      alert(`Binding save error: ${err.message || err}`);
    }
  };

  const handleRunTestCase = async () => {
    if (!selectedCase || !selectedProjectId || runningCase) return;
    try {
      setRunningCase(true);
      setRunMessage('Triggering execution run...');
      const target = selectedBinding ? [selectedBinding.test_node_id] : undefined;
      const run = await api.createTestRun({
        project_id: selectedProjectId,
        target_nodeids: target,
        triggered_by: `Test Case: ${selectedCase.title}`,
      });
      setRunMessage(`Execution dispatched as Run #${run.id.slice(0, 8)} (${run.status})`);
      if (onNavigateToRuns) {
        setTimeout(() => onNavigateToRuns(run.id), 1200);
      }
    } catch (err: any) {
      setRunMessage(`Execution error: ${err.message || err}`);
    } finally {
      setRunningCase(false);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
        <div>
          <h2 style={{ fontSize: '18px', fontWeight: 700 }}>Test Case & Automation Binding</h2>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            Manage test cases, generate AI Playwright code, and link business tests to executable pytest node IDs.
          </p>
        </div>
        <button
          className="btn btn-primary"
          disabled={projects.length === 0}
          onClick={() => {
            setFormData({
              ...formData,
              project_id: selectedProjectId || projects[0]?.id || '',
            });
            setIsModalOpen(true);
          }}
        >
          <Plus size={16} /> New Test Case
        </button>
      </div>

      {projects.length === 0 ? (
        <div className="card">
          <div className="card-body" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
            Please create a project first before adding test cases.
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1.8fr', gap: '20px' }}>
          {/* Test Cases List */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">Test Cases ({testCases.length})</span>
            </div>
            <div className="card-body" style={{ padding: 0 }}>
              {loading ? (
                <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  Loading test cases...
                </div>
              ) : testCases.length === 0 ? (
                <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  No test cases found.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  {testCases.map((tc) => {
                    const isSelected = selectedCase?.id === tc.id;
                    return (
                      <div
                        key={tc.id}
                        onClick={() => handleSelectCase(tc)}
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
                          <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-main)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {tc.title}
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px', flexWrap: 'wrap' }}>
                            <span className={`badge badge-${tc.priority.toLowerCase()}`}>{tc.priority}</span>
                            <span className={`badge badge-${tc.automation_status.toLowerCase()}`}>
                              {tc.automation_status}
                            </span>
                            {tc.external_case_id && (
                              <span style={{ fontSize: '10px', background: '#ecfdf5', color: '#047857', padding: '1px 5px', borderRadius: '3px', fontWeight: 600 }}>
                                TestRail: {tc.external_case_id}
                              </span>
                            )}
                            {tc.tags && tc.tags.slice(0, 2).map((tag, idx) => (
                              <span key={idx} className="badge badge-draft" style={{ fontSize: '10px' }}>
                                #{tag}
                              </span>
                            ))}
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

          {/* Test Case Details & Automation Studio Binding */}
          {selectedCase ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div className="card">
                <div className="card-header">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                    <CheckSquare size={16} color="#16a34a" />
                    <span className="card-title">{selectedCase.title}</span>
                    {selectedCase.external_case_id && (
                      <a
                        href={selectedCase.external_url || `https://testrail.example.com/index.php?/cases/view/${selectedCase.external_case_id.replace(/^C/i, '')}`}
                        target="_blank"
                        rel="noreferrer"
                        style={{ fontSize: '11px', background: '#ecfdf5', color: '#047857', padding: '2px 8px', borderRadius: '4px', textDecoration: 'none', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                      >
                        {selectedCase.external_case_id} <ExternalLink size={11} />
                      </a>
                    )}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className={`badge badge-${selectedCase.priority.toLowerCase()}`}>
                      {selectedCase.priority}
                    </span>
                    <select
                      className="form-control"
                      style={{ padding: '3px 8px', fontSize: '12px', width: '130px' }}
                      value={selectedCase.automation_status}
                      onChange={(e) =>
                        handleUpdateStatus(selectedCase.id, e.target.value as AutomationStatus)
                      }
                    >
                      <option value="MANUAL">MANUAL</option>
                      <option value="DRAFT">DRAFT</option>
                      <option value="AUTOMATED">AUTOMATED</option>
                    </select>
                  </div>
                </div>
                <div className="card-body">
                  {selectedCase.preconditions && (
                    <div style={{ marginBottom: '14px' }}>
                      <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
                        Preconditions
                      </div>
                      <div style={{ fontSize: '13px', color: '#334155', background: '#f8fafc', padding: '8px 12px', borderRadius: '4px' }}>
                        {selectedCase.preconditions}
                      </div>
                    </div>
                  )}

                  <div style={{ marginBottom: '14px' }}>
                    <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
                      Test Steps ({selectedCase.steps.length})
                    </div>
                    {selectedCase.steps.length > 0 ? (
                      <ol style={{ paddingLeft: '20px', fontSize: '13px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        {selectedCase.steps.map((st, i) => (
                          <li key={i} style={{ color: '#1e293b' }}>
                            {st}
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>No explicit steps recorded.</div>
                    )}
                  </div>

                  <div style={{ marginBottom: '14px' }}>
                    <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
                      Expected Result
                    </div>
                    <div style={{ fontSize: '13px', color: '#334155', background: '#f0fdf4', border: '1px solid #bbf7d0', padding: '8px 12px', borderRadius: '4px' }}>
                      {selectedCase.expected_result || 'No expected result specified.'}
                    </div>
                  </div>

                  {selectedCase.tags.length > 0 && (
                    <div>
                      <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
                        Tags
                      </div>
                      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                        {selectedCase.tags.map((t, idx) => (
                          <span key={idx} className="badge badge-draft">
                            <Tag size={10} style={{ marginRight: '4px' }} /> {t}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Automation Binding Card */}
              <div className="card">
                <div className="card-header">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Code2 size={16} color="#2563eb" />
                    <span className="card-title">Automation Binding & Execution</span>
                  </div>
                  <div style={{ display: 'flex', gap: '6px' }}>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => setIsBindingModalOpen(true)}
                    >
                      <Edit3 size={13} /> {selectedBinding ? 'Edit Binding' : 'Configure Binding'}
                    </button>
                  </div>
                </div>
                <div className="card-body">
                  {selectedBinding ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', background: '#f8fafc', padding: '12px', borderRadius: '6px', border: '1px solid var(--border-color)' }}>
                        <div>
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600 }}>Target Test File</div>
                          <div style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', color: '#0f172a', marginTop: '2px' }}>
                            {selectedBinding.test_file_path}
                          </div>
                        </div>
                        <div>
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600 }}>Pytest Node ID</div>
                          <div style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', color: '#0f172a', marginTop: '2px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {selectedBinding.test_node_id}
                          </div>
                        </div>
                      </div>

                      {/* Action Buttons */}
                      <div style={{ display: 'flex', gap: '8px', marginTop: '4px' }}>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => onNavigateToStudio && onNavigateToStudio(selectedBinding.test_file_path)}
                        >
                          <ExternalLink size={13} /> Open in Studio
                        </button>
                        <button
                          className="btn btn-primary btn-sm"
                          disabled={runningCase}
                          onClick={handleRunTestCase}
                        >
                          <Play size={13} /> {runningCase ? 'Running...' : 'Run Test Now'}
                        </button>
                        <button
                          className="btn btn-secondary btn-sm"
                          disabled={generating}
                          onClick={handleGenerateAutomation}
                        >
                          <Sparkles size={13} color="#9333ea" /> Re-generate AI Code
                        </button>
                      </div>

                      {runMessage && (
                        <div style={{ marginTop: '8px', padding: '8px 12px', background: '#eff6ff', borderRadius: '4px', fontSize: '12px', color: '#1d4ed8' }}>
                          {runMessage}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div style={{ textAlign: 'center', padding: '16px' }}>
                      <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '14px' }}>
                        This test case is currently manual and not yet bound to an automated test file.
                      </p>
                      <div style={{ display: 'flex', justifyContent: 'center', gap: '10px' }}>
                        <button
                          className="btn btn-primary"
                          disabled={generating}
                          onClick={handleGenerateAutomation}
                        >
                          <Sparkles size={15} /> {generating ? 'Generating Playwright Code...' : 'Generate Automation Scaffold'}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* AI Generated Code Preview */}
                  {generatedDraft && (
                    <div style={{ marginTop: '18px', borderTop: '1px solid var(--border-color)', paddingTop: '16px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                        <div style={{ fontSize: '12px', fontWeight: 700, color: '#334155' }}>
                          AI Generated Test Scaffold ({generatedDraft.target_file})
                        </div>
                        <button
                          className="btn btn-primary btn-sm"
                          disabled={savingDraft}
                          onClick={handleSaveDraftToWorkspace}
                        >
                          <CheckCircle size={13} /> {savingDraft ? 'Saving to Workspace...' : 'Save & Bind to Workspace'}
                        </button>
                      </div>
                      <div
                        style={{
                          background: '#0f172a',
                          color: '#f8fafc',
                          padding: '12px',
                          borderRadius: '6px',
                          fontFamily: 'var(--font-mono)',
                          fontSize: '12px',
                          overflowX: 'auto',
                          maxHeight: '260px',
                        }}
                      >
                        <pre>{generatedDraft.suggested_code}</pre>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Quality Intelligence & Execution History Card */}
              {selectedBinding && (
                <div className="card">
                  <div className="card-header">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span className="card-title">Quality Intelligence & Execution History</span>
                    </div>
                    {caseHistory && (
                      <span className="badge badge-ready" style={{ fontSize: '11px' }}>
                        Stability: {caseHistory.flaky_score.classification} (Score: {caseHistory.flaky_score.score.toFixed(2)})
                      </span>
                    )}
                  </div>
                  <div className="card-body">
                    {loadingCaseHistory ? (
                      <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
                        Loading execution history...
                      </div>
                    ) : caseHistory && caseHistory.executions.length > 0 ? (
                      <div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px', marginBottom: '14px', textAlign: 'center' }}>
                          <div style={{ background: '#f8fafc', padding: '8px', borderRadius: '4px' }}>
                            <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Pass / Fail</div>
                            <div style={{ fontSize: '14px', fontWeight: 700, marginTop: '2px' }}>
                              <span style={{ color: '#16a34a' }}>{caseHistory.trend.pass_count}</span> /{' '}
                              <span style={{ color: '#dc2626' }}>{caseHistory.trend.fail_count}</span>
                            </div>
                          </div>
                          <div style={{ background: '#f8fafc', padding: '8px', borderRadius: '4px' }}>
                            <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Avg Duration</div>
                            <div style={{ fontSize: '14px', fontWeight: 700, marginTop: '2px' }}>
                              {(caseHistory.trend.average_duration_ms / 1000).toFixed(2)}s
                            </div>
                          </div>
                          <div style={{ background: '#f8fafc', padding: '8px', borderRadius: '4px' }}>
                            <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>P95 Duration</div>
                            <div style={{ fontSize: '14px', fontWeight: 700, marginTop: '2px' }}>
                              {(caseHistory.trend.p95_duration_ms / 1000).toFixed(2)}s
                            </div>
                          </div>
                          <div style={{ background: '#f8fafc', padding: '8px', borderRadius: '4px' }}>
                            <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Confidence</div>
                            <div style={{ fontSize: '14px', fontWeight: 700, marginTop: '2px' }}>
                              {(caseHistory.flaky_score.confidence * 100).toFixed(0)}%
                            </div>
                          </div>
                        </div>

                        <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
                          Recent Executions
                        </div>
                        <table className="data-table" style={{ fontSize: '11px' }}>
                          <thead>
                            <tr>
                              <th style={{ padding: '6px 8px' }}>Status</th>
                              <th style={{ padding: '6px 8px' }}>Run ID</th>
                              <th style={{ padding: '6px 8px' }}>Duration</th>
                              <th style={{ padding: '6px 8px' }}>Root Category</th>
                              <th style={{ padding: '6px 8px' }}>Error Details</th>
                            </tr>
                          </thead>
                          <tbody>
                            {caseHistory.executions.slice(0, 5).map((e: any) => (
                              <tr key={e.id}>
                                <td style={{ padding: '6px 8px' }}>
                                  <span className={`badge badge-${e.status === 'PASSED' ? 'ready' : 'p0'}`}>
                                    {e.status}
                                  </span>
                                </td>
                                <td style={{ padding: '6px 8px', fontFamily: 'var(--font-mono)' }}>
                                  #{e.run_id.slice(0, 8)}
                                </td>
                                <td style={{ padding: '6px 8px' }}>{(e.duration_ms / 1000).toFixed(2)}s</td>
                                <td style={{ padding: '6px 8px', color: 'var(--text-muted)' }}>
                                  {e.failure_category || '—'}
                                </td>
                                <td style={{ padding: '6px 8px', color: e.error_message ? '#dc2626' : 'var(--text-muted)' }}>
                                  {e.error_message ? e.error_message.slice(0, 60) + '...' : '—'}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <div style={{ padding: '12px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
                        No execution history recorded for this node ID yet. Trigger a run to record runs.
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="card">
              <div className="card-body" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
                Select a test case to view step details and automation bindings.
              </div>
            </div>
          )}
        </div>
      )}

      {/* Manual Automation Binding Modal */}
      {isBindingModalOpen && (
        <div className="modal-overlay">
          <div className="modal-dialog">
            <form onSubmit={handleSaveManualBinding}>
              <div className="modal-header">
                <h3 style={{ fontSize: '15px', fontWeight: 700 }}>Configure Automation Binding</h3>
                <button
                  type="button"
                  style={{ background: 'none', border: 'none', cursor: 'pointer' }}
                  onClick={() => setIsBindingModalOpen(false)}
                >
                  ✕
                </button>
              </div>
              <div className="modal-body" style={{ padding: '20px' }}>
                <div className="form-group">
                  <label className="form-label">Test File Path *</label>
                  <input
                    type="text"
                    required
                    className="form-control"
                    placeholder="e.g. tests/test_checkout.py"
                    value={bindingFormData.test_file_path}
                    onChange={(e) =>
                      setBindingFormData({ ...bindingFormData, test_file_path: e.target.value })
                    }
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Pytest Node ID *</label>
                  <input
                    type="text"
                    required
                    className="form-control"
                    placeholder="e.g. tests/test_checkout.py::test_coupon_calculation"
                    value={bindingFormData.test_node_id}
                    onChange={(e) =>
                      setBindingFormData({ ...bindingFormData, test_node_id: e.target.value })
                    }
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Automation Status</label>
                  <select
                    className="form-control"
                    value={bindingFormData.status}
                    onChange={(e) =>
                      setBindingFormData({
                        ...bindingFormData,
                        status: e.target.value as AutomationStatus,
                      })
                    }
                  >
                    <option value="MANUAL">MANUAL</option>
                    <option value="DRAFT">DRAFT</option>
                    <option value="AUTOMATED">AUTOMATED</option>
                  </select>
                </div>
              </div>
              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsBindingModalOpen(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Save Binding
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Create Test Case Modal */}
      {isModalOpen && (
        <div className="modal-overlay">
          <div className="modal-dialog">
            <form onSubmit={handleCreateTestCase}>
              <div className="modal-header">
                <h3 style={{ fontSize: '15px', fontWeight: 700 }}>New Test Case</h3>
                <button
                  type="button"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '16px' }}
                  onClick={() => setIsModalOpen(false)}
                >
                  ✕
                </button>
              </div>
              <div className="modal-body" style={{ padding: '20px' }}>
                <div className="form-group">
                  <label className="form-label">Project *</label>
                  <select
                    className="form-control"
                    value={formData.project_id}
                    onChange={(e) => setFormData({ ...formData, project_id: e.target.value })}
                  >
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Test Case Title *</label>
                  <input
                    type="text"
                    required
                    className="form-control"
                    placeholder="e.g. Verify checkout calculation with 10% coupon"
                    value={formData.title}
                    onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div className="form-group">
                    <label className="form-label">Priority</label>
                    <select
                      className="form-control"
                      value={formData.priority}
                      onChange={(e) =>
                        setFormData({ ...formData, priority: e.target.value as TestCasePriority })
                      }
                    >
                      <option value="P0">P0 - Blocker</option>
                      <option value="P1">P1 - Critical</option>
                      <option value="P2">P2 - Major</option>
                      <option value="P3">P3 - Minor</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Automation Status</label>
                    <select
                      className="form-control"
                      value={formData.automation_status}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          automation_status: e.target.value as AutomationStatus,
                        })
                      }
                    >
                      <option value="MANUAL">MANUAL</option>
                      <option value="DRAFT">DRAFT</option>
                      <option value="AUTOMATED">AUTOMATED</option>
                    </select>
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Preconditions</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="e.g. User is logged in as standard customer..."
                    value={formData.preconditions}
                    onChange={(e) => setFormData({ ...formData, preconditions: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Steps (One step per line)</label>
                  <textarea
                    rows={4}
                    className="form-control"
                    placeholder="1. Open product page&#10;2. Click Add to Cart&#10;3. Navigate to checkout"
                    value={stepsText}
                    onChange={(e) => setStepsText(e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Expected Result</label>
                  <textarea
                    rows={2}
                    className="form-control"
                    placeholder="Final total is reduced by exactly 10%."
                    value={formData.expected_result}
                    onChange={(e) => setFormData({ ...formData, expected_result: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Tags (comma separated)</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="smoke, checkout, cart"
                    value={tagsText}
                    onChange={(e) => setTagsText(e.target.value)}
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsModalOpen(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Save Test Case
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
