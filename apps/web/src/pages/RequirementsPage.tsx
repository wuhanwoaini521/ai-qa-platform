import React, { useEffect, useState } from 'react';
import {
  Project,
  Requirement,
  RequirementAnalysisDTO,
  RequirementCreate,
  RequirementStatus,
  TestCaseGenerationItem,
  TestDesign,
  TestDesignCategory,
  TestDesignCreate,
  TestDesignSuggestion,
} from '../types';
import { api } from '../api/client';
import {
  Plus,
  FileText,
  Layers,
  ChevronRight,
  Sparkles,
  AlertTriangle,
  HelpCircle,
  RefreshCw,
  ListChecks,
} from 'lucide-react';

interface RequirementsPageProps {
  projects: Project[];
  selectedProjectId: string | null;
  onNavigateToStudio?: (filePath: string) => void;
}

export const RequirementsPage: React.FC<RequirementsPageProps> = ({
  projects,
  selectedProjectId,
}) => {
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedReq, setSelectedReq] = useState<Requirement | null>(null);
  const [testDesigns, setTestDesigns] = useState<TestDesign[]>([]);

  // AI Analysis Modal
  const [isAiAnalysisOpen, setIsAiAnalysisOpen] = useState(false);
  const [aiAnalysis, setAiAnalysis] = useState<RequirementAnalysisDTO | null>(null);
  const [analyzingReq, setAnalyzingReq] = useState(false);

  // AI Test Design Generation Modal
  const [isAiDesignModalOpen, setIsAiDesignModalOpen] = useState(false);
  const [suggestedDesigns, setSuggestedDesigns] = useState<TestDesignSuggestion[]>([]);
  const [generatingDesigns, setGeneratingDesigns] = useState(false);

  // AI Test Case Generation Modal
  const [isAiCaseModalOpen, setIsAiCaseModalOpen] = useState(false);
  const [suggestedCases, setSuggestedCases] = useState<TestCaseGenerationItem[]>([]);
  const [generatingCases, setGeneratingCases] = useState(false);
  const [activeDesignForCases, setActiveDesignForCases] = useState<TestDesign | null>(null);

  // Manual Modals
  const [isReqModalOpen, setIsReqModalOpen] = useState(false);
  const [isDesignModalOpen, setIsDesignModalOpen] = useState(false);

  const [reqFormData, setReqFormData] = useState<RequirementCreate>({
    project_id: selectedProjectId || (projects[0]?.id ?? ''),
    title: '',
    description: '',
    acceptance_criteria: '',
    status: 'DRAFT',
  });

  const [designFormData, setDesignFormData] = useState<TestDesignCreate>({
    requirement_id: '',
    title: '',
    category: 'FUNCTIONAL',
    description: '',
    risk: 'Medium',
    status: 'DRAFT',
  });

  const fetchRequirements = async () => {
    try {
      setLoading(true);
      const data = await api.getRequirements(selectedProjectId || undefined);
      setRequirements(data);
      if (data.length > 0 && !selectedReq) {
        setSelectedReq(data[0]);
      }
    } catch (err) {
      console.error('Failed to load requirements', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchTestDesigns = async (reqId: string) => {
    try {
      const data = await api.getTestDesigns(reqId);
      setTestDesigns(data);
    } catch (err) {
      console.error('Failed to load test designs', err);
    }
  };

  useEffect(() => {
    fetchRequirements();
  }, [selectedProjectId]);

  useEffect(() => {
    if (selectedReq) {
      fetchTestDesigns(selectedReq.id);
    } else {
      setTestDesigns([]);
    }
  }, [selectedReq]);

  const handleAnalyzeRequirementAI = async () => {
    if (!selectedReq) return;
    try {
      setAnalyzingReq(true);
      setIsAiAnalysisOpen(true);
      const res = await api.analyzeRequirement(selectedReq.id);
      setAiAnalysis(res);
    } catch (err) {
      console.error('AI Requirement analysis failed', err);
    } finally {
      setAnalyzingReq(false);
    }
  };

  const handleGenerateDesignsAI = async () => {
    if (!selectedReq) return;
    try {
      setGeneratingDesigns(true);
      setIsAiDesignModalOpen(true);
      const res = await api.generateTestDesigns(selectedReq.id);
      setSuggestedDesigns(res);
    } catch (err) {
      console.error('AI Test Design generation failed', err);
    } finally {
      setGeneratingDesigns(false);
    }
  };

  const handleAdoptDesign = async (suggestion: TestDesignSuggestion) => {
    if (!selectedReq) return;
    try {
      const created = await api.createTestDesign({
        requirement_id: selectedReq.id,
        title: suggestion.title,
        category: suggestion.category as TestDesignCategory,
        description: suggestion.description,
        risk: suggestion.risk,
        status: 'DRAFT',
      });
      setTestDesigns([...testDesigns, created]);
      setSuggestedDesigns(suggestedDesigns.filter((s) => s.title !== suggestion.title));
    } catch (err) {
      console.error('Failed to adopt test design', err);
    }
  };

  const handleGenerateCasesAI = async (design: TestDesign) => {
    try {
      setActiveDesignForCases(design);
      setGeneratingCases(true);
      setIsAiCaseModalOpen(true);
      const res = await api.generateTestCases(design.id);
      setSuggestedCases(res);
    } catch (err) {
      console.error('AI Test Case generation failed', err);
    } finally {
      setGeneratingCases(false);
    }
  };

  const handleAdoptCase = async (item: TestCaseGenerationItem) => {
    if (!selectedReq || !activeDesignForCases) return;
    try {
      await api.createTestCase({
        project_id: selectedReq.project_id,
        requirement_id: selectedReq.id,
        test_design_id: activeDesignForCases.id,
        title: item.title,
        preconditions: item.preconditions,
        steps: item.steps,
        expected_result: item.expected_result,
        priority: item.priority as any,
        tags: item.tags,
        automation_status: 'DRAFT',
      });
      setSuggestedCases(suggestedCases.filter((c) => c.title !== item.title));
    } catch (err) {
      console.error('Failed to adopt test case', err);
    }
  };

  const handleCreateRequirement = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reqFormData.title.trim()) return;
    try {
      const created = await api.createRequirement({
        ...reqFormData,
        project_id: selectedProjectId || reqFormData.project_id || projects[0]?.id || '',
      });
      setRequirements([created, ...requirements]);
      setSelectedReq(created);
      setIsReqModalOpen(false);
      setReqFormData({
        project_id: selectedProjectId || (projects[0]?.id ?? ''),
        title: '',
        description: '',
        acceptance_criteria: '',
        status: 'DRAFT',
      });
    } catch (err) {
      console.error('Failed to create requirement', err);
    }
  };

  const handleCreateTestDesign = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedReq || !designFormData.title.trim()) return;
    try {
      const created = await api.createTestDesign({
        ...designFormData,
        requirement_id: selectedReq.id,
      });
      setTestDesigns([created, ...testDesigns]);
      setIsDesignModalOpen(false);
      setDesignFormData({
        requirement_id: '',
        title: '',
        category: 'FUNCTIONAL',
        description: '',
        risk: 'Medium',
        status: 'DRAFT',
      });
    } catch (err) {
      console.error('Failed to create test design', err);
    }
  };

  const handleUpdateStatus = async (reqId: string, status: RequirementStatus) => {
    try {
      const updated = await api.updateRequirement(reqId, { status });
      setRequirements(requirements.map((r) => (r.id === reqId ? updated : r)));
      if (selectedReq?.id === reqId) {
        setSelectedReq(updated);
      }
    } catch (err) {
      console.error('Failed to update requirement status', err);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
        <div>
          <h2 style={{ fontSize: '18px', fontWeight: 700 }}>Requirement & AI Test Design</h2>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            AI-assisted requirement testability analysis, risk extraction, and dimensional test design generation.
          </p>
        </div>
        <button
          className="btn btn-primary"
          disabled={projects.length === 0}
          onClick={() => {
            setReqFormData({
              ...reqFormData,
              project_id: selectedProjectId || projects[0]?.id || '',
            });
            setIsReqModalOpen(true);
          }}
        >
          <Plus size={16} /> New Requirement
        </button>
      </div>

      {projects.length === 0 ? (
        <div className="card">
          <div className="card-body" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
            Please create a project first before creating requirements.
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.6fr', gap: '20px' }}>
          {/* Requirement List */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">Requirements ({requirements.length})</span>
            </div>
            <div className="card-body" style={{ padding: 0 }}>
              {loading ? (
                <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  Loading requirements...
                </div>
              ) : requirements.length === 0 ? (
                <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  No requirements found for this project.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  {requirements.map((r) => {
                    const isSelected = selectedReq?.id === r.id;
                    return (
                      <div
                        key={r.id}
                        onClick={() => setSelectedReq(r)}
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
                            {r.title}
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
                            <span className="status-pill status-pill-draft">{r.status}</span>
                            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                              {new Date(r.created_at).toLocaleDateString()}
                            </span>
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

          {/* Requirement Details & Test Designs */}
          {selectedReq ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div className="card">
                <div className="card-header">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <FileText size={16} color="#2563eb" />
                    <span className="card-title">{selectedReq.title}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <button className="btn btn-secondary btn-sm" onClick={handleAnalyzeRequirementAI}>
                      <Sparkles size={13} color="var(--color-primary)" />
                      <span>AI Analyze</span>
                    </button>
                    <select
                      className="form-select"
                      style={{ padding: '3px 8px', fontSize: '12px', width: 'auto', margin: 0 }}
                      value={selectedReq.status}
                      onChange={(e) => handleUpdateStatus(selectedReq.id, e.target.value as RequirementStatus)}
                    >
                      <option value="DRAFT">DRAFT</option>
                      <option value="READY">READY</option>
                      <option value="ARCHIVED">ARCHIVED</option>
                    </select>
                  </div>
                </div>
                <div className="card-body">
                  <div style={{ marginBottom: '14px' }}>
                    <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
                      Description
                    </div>
                    <div style={{ fontSize: '13px', color: '#334155', whiteSpace: 'pre-wrap' }}>
                      {selectedReq.description || 'No description provided.'}
                    </div>
                  </div>

                  <div>
                    <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
                      Acceptance Criteria
                    </div>
                    <div
                      style={{
                        fontSize: '13px',
                        background: '#f8fafc',
                        padding: '10px 14px',
                        borderRadius: '4px',
                        border: '1px solid var(--border-color)',
                        fontFamily: 'monospace',
                        whiteSpace: 'pre-wrap',
                      }}
                    >
                      {selectedReq.acceptance_criteria || 'No acceptance criteria specified.'}
                    </div>
                  </div>
                </div>
              </div>

              {/* Test Designs for this Requirement */}
              <div className="card">
                <div className="card-header">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Layers size={16} color="#16a34a" />
                    <span className="card-title">Test Designs ({testDesigns.length})</span>
                  </div>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button className="btn btn-primary btn-sm" onClick={handleGenerateDesignsAI}>
                      <Sparkles size={13} />
                      <span>AI Generate Designs</span>
                    </button>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => {
                        setDesignFormData({ ...designFormData, requirement_id: selectedReq.id });
                        setIsDesignModalOpen(true);
                      }}
                    >
                      <Plus size={13} /> Add Manual Design
                    </button>
                  </div>
                </div>
                <div className="card-body" style={{ padding: 0 }}>
                  {testDesigns.length === 0 ? (
                    <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
                      No test designs yet. Click <strong>AI Generate Designs</strong> to produce structured functional, boundary, and negative dimensions.
                    </div>
                  ) : (
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Design Title</th>
                          <th>Category</th>
                          <th>Risk</th>
                          <th>Status</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {testDesigns.map((td) => (
                          <tr key={td.id}>
                            <td style={{ fontWeight: 500 }}>{td.title}</td>
                            <td>
                              <span className="status-pill status-pill-draft">{td.category}</span>
                            </td>
                            <td>{td.risk}</td>
                            <td>
                              <span className="status-pill status-pill-passed">{td.status}</span>
                            </td>
                            <td>
                              <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => handleGenerateCasesAI(td)}
                              >
                                <ListChecks size={12} />
                                <span>AI Generate Cases</span>
                              </button>
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
                Select a requirement to view details.
              </div>
            </div>
          )}
        </div>
      )}

      {/* AI Requirement Analysis Modal */}
      {isAiAnalysisOpen && (
        <div className="modal-overlay">
          <div className="modal-card" style={{ maxWidth: '650px' }}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Sparkles size={18} color="var(--color-primary)" />
                <h3>AI Requirement Testability Analysis</h3>
              </div>
              <button className="btn btn-secondary btn-sm" onClick={() => setIsAiAnalysisOpen(false)}>
                Close
              </button>
            </div>
            <div className="modal-body">
              {analyzingReq ? (
                <div style={{ padding: '2rem', textAlign: 'center' }}>
                  <RefreshCw size={24} className="spinning" style={{ marginBottom: '0.75rem' }} />
                  <div>Analyzing requirement testability dimensions...</div>
                </div>
              ) : aiAnalysis ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <div>
                    <h4 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                      Executive Testing Summary
                    </h4>
                    <p style={{ marginTop: '0.25rem', fontSize: '0.9rem' }}>{aiAnalysis.summary}</p>
                  </div>

                  <div>
                    <h4 style={{ fontSize: '0.85rem', color: 'var(--color-error)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <AlertTriangle size={14} /> Identified Quality Risks
                    </h4>
                    <ul style={{ paddingLeft: '1.25rem', marginTop: '0.25rem', fontSize: '0.85rem' }}>
                      {aiAnalysis.risks.map((risk, idx) => (
                        <li key={idx} style={{ marginBottom: '0.25rem' }}>{risk}</li>
                      ))}
                    </ul>
                  </div>

                  <div>
                    <h4 style={{ fontSize: '0.85rem', color: 'var(--color-warning)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <HelpCircle size={14} /> Ambiguities & Missing Specs
                    </h4>
                    <ul style={{ paddingLeft: '1.25rem', marginTop: '0.25rem', fontSize: '0.85rem' }}>
                      {aiAnalysis.ambiguities.map((amb, idx) => (
                        <li key={idx} style={{ marginBottom: '0.25rem' }}>{amb}</li>
                      ))}
                    </ul>
                  </div>

                  <div>
                    <h4 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                      Recommended Coverage Dimensions
                    </h4>
                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '0.4rem' }}>
                      {aiAnalysis.suggested_test_dimensions.map((dim, idx) => (
                        <span key={idx} className="status-pill status-pill-draft">{dim}</span>
                      ))}
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      )}

      {/* AI Test Design Generation Modal */}
      {isAiDesignModalOpen && (
        <div className="modal-overlay">
          <div className="modal-card" style={{ maxWidth: '750px' }}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Sparkles size={18} color="var(--color-primary)" />
                <h3>AI Generated Test Design Candidates</h3>
              </div>
              <button className="btn btn-secondary btn-sm" onClick={() => setIsAiDesignModalOpen(false)}>
                Close
              </button>
            </div>
            <div className="modal-body">
              {generatingDesigns ? (
                <div style={{ padding: '2rem', textAlign: 'center' }}>
                  <RefreshCw size={24} className="spinning" style={{ marginBottom: '0.75rem' }} />
                  <div>Generating functional, boundary, negative, and API test designs...</div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  {suggestedDesigns.map((sug, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: '1rem',
                        background: 'var(--bg-subtle)',
                        borderRadius: '6px',
                        border: '1px solid var(--border-color)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <div style={{ flex: 1, paddingRight: '1rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span className="status-pill status-pill-draft">{sug.category}</span>
                          <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>{sug.title}</span>
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Risk: {sug.risk}</span>
                        </div>
                        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.35rem' }}>
                          {sug.description}
                        </p>
                      </div>
                      <button className="btn btn-primary btn-sm" onClick={() => handleAdoptDesign(sug)}>
                        Adopt Design
                      </button>
                    </div>
                  ))}
                  {suggestedDesigns.length === 0 && (
                    <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                      All design candidates adopted or none generated.
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* AI Test Case Generation Modal */}
      {isAiCaseModalOpen && (
        <div className="modal-overlay">
          <div className="modal-card" style={{ maxWidth: '750px' }}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Sparkles size={18} color="var(--color-primary)" />
                <div>
                  <h3>AI Generated Test Cases</h3>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Design: {activeDesignForCases?.title}
                  </div>
                </div>
              </div>
              <button className="btn btn-secondary btn-sm" onClick={() => setIsAiCaseModalOpen(false)}>
                Close
              </button>
            </div>
            <div className="modal-body">
              {generatingCases ? (
                <div style={{ padding: '2rem', textAlign: 'center' }}>
                  <RefreshCw size={24} className="spinning" style={{ marginBottom: '0.75rem' }} />
                  <div>Generating concrete test case steps, preconditions, and assertions...</div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  {suggestedCases.map((c, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: '1rem',
                        background: 'var(--bg-subtle)',
                        borderRadius: '6px',
                        border: '1px solid var(--border-color)',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                          <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{c.title}</div>
                          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                            Priority: <strong>{c.priority}</strong> | Tags: {c.tags.join(', ')}
                          </div>
                        </div>
                        <button className="btn btn-primary btn-sm" onClick={() => handleAdoptCase(c)}>
                          Adopt as Draft Case
                        </button>
                      </div>
                      <div style={{ marginTop: '0.5rem', fontSize: '0.8rem' }}>
                        <div style={{ fontWeight: 500 }}>Steps:</div>
                        <ol style={{ paddingLeft: '1.25rem', margin: '0.25rem 0' }}>
                          {c.steps.map((s, i) => (
                            <li key={i}>{s}</li>
                          ))}
                        </ol>
                        <div style={{ color: 'var(--text-muted)' }}>
                          <strong>Expected:</strong> {c.expected_result}
                        </div>
                      </div>
                    </div>
                  ))}
                  {suggestedCases.length === 0 && (
                    <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                      All generated cases adopted.
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Create Requirement Modal */}
      {isReqModalOpen && (
        <div className="modal-overlay">
          <div className="modal-card">
            <form onSubmit={handleCreateRequirement}>
              <div className="modal-header">
                <h3>New Requirement</h3>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setIsReqModalOpen(false)}
                >
                  ✕
                </button>
              </div>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Project *</label>
                  <select
                    className="form-select"
                    value={reqFormData.project_id}
                    onChange={(e) => setReqFormData({ ...reqFormData, project_id: e.target.value })}
                  >
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Title *</label>
                  <input
                    type="text"
                    required
                    className="form-input"
                    placeholder="e.g. User Authentication & Password Reset"
                    value={reqFormData.title}
                    onChange={(e) => setReqFormData({ ...reqFormData, title: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Description</label>
                  <textarea
                    rows={3}
                    className="form-textarea"
                    placeholder="Detailed explanation of the feature or requirement..."
                    value={reqFormData.description}
                    onChange={(e) => setReqFormData({ ...reqFormData, description: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Acceptance Criteria</label>
                  <textarea
                    rows={3}
                    className="form-textarea"
                    placeholder="Given ..., When ..., Then ..."
                    value={reqFormData.acceptance_criteria}
                    onChange={(e) =>
                      setReqFormData({ ...reqFormData, acceptance_criteria: e.target.value })
                    }
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Initial Status</label>
                  <select
                    className="form-select"
                    value={reqFormData.status}
                    onChange={(e) =>
                      setReqFormData({ ...reqFormData, status: e.target.value as RequirementStatus })
                    }
                  >
                    <option value="DRAFT">DRAFT</option>
                    <option value="READY">READY</option>
                    <option value="ARCHIVED">ARCHIVED</option>
                  </select>
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsReqModalOpen(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Save Requirement
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Create Test Design Modal */}
      {isDesignModalOpen && (
        <div className="modal-overlay">
          <div className="modal-card">
            <form onSubmit={handleCreateTestDesign}>
              <div className="modal-header">
                <h3>Add Test Design</h3>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setIsDesignModalOpen(false)}
                >
                  ✕
                </button>
              </div>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Design Title *</label>
                  <input
                    type="text"
                    required
                    className="form-input"
                    placeholder="e.g. Boundary Test: Negative Input Handling"
                    value={designFormData.title}
                    onChange={(e) => setDesignFormData({ ...designFormData, title: e.target.value })}
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div className="form-group">
                    <label className="form-label">Category</label>
                    <select
                      className="form-select"
                      value={designFormData.category}
                      onChange={(e) =>
                        setDesignFormData({
                          ...designFormData,
                          category: e.target.value as TestDesignCategory,
                        })
                      }
                    >
                      <option value="FUNCTIONAL">FUNCTIONAL</option>
                      <option value="BOUNDARY">BOUNDARY</option>
                      <option value="NEGATIVE">NEGATIVE</option>
                      <option value="ANALYTICS">ANALYTICS</option>
                      <option value="API">API</option>
                      <option value="UI">UI</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Risk Level</label>
                    <select
                      className="form-select"
                      value={designFormData.risk}
                      onChange={(e) => setDesignFormData({ ...designFormData, risk: e.target.value })}
                    >
                      <option value="Low">Low</option>
                      <option value="Medium">Medium</option>
                      <option value="High">High</option>
                      <option value="Critical">Critical</option>
                    </select>
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Design Details</label>
                  <textarea
                    rows={3}
                    className="form-textarea"
                    placeholder="Describe specific scenario permutations..."
                    value={designFormData.description}
                    onChange={(e) =>
                      setDesignFormData({ ...designFormData, description: e.target.value })
                    }
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setIsDesignModalOpen(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Save Design
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
