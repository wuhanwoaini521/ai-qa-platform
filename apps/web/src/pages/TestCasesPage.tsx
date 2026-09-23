import React, { useEffect, useState } from 'react';
import { AutomationStatus, Project, TestCase, TestCaseCreate, TestCasePriority } from '../types';
import { api } from '../api/client';
import { Plus, CheckSquare, Tag, ChevronRight } from 'lucide-react';

interface TestCasesPageProps {
  projects: Project[];
  selectedProjectId: string | null;
}

export const TestCasesPage: React.FC<TestCasesPageProps> = ({ projects, selectedProjectId }) => {
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCase, setSelectedCase] = useState<TestCase | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

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
      if (data.length > 0 && !selectedCase) {
        setSelectedCase(data[0]);
      }
    } catch (err) {
      console.error('Failed to load test cases', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTestCases();
  }, [selectedProjectId]);

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

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
        <div>
          <h2 style={{ fontSize: '18px', fontWeight: 700 }}>Test Case Management</h2>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            Platform test cases (business entities) linked to requirements and automation status.
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
                        onClick={() => setSelectedCase(tc)}
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
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px' }}>
                            <span className={`badge badge-${tc.priority.toLowerCase()}`}>{tc.priority}</span>
                            <span className={`badge badge-${tc.automation_status.toLowerCase()}`}>
                              {tc.automation_status}
                            </span>
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

          {/* Test Case Details */}
          {selectedCase ? (
            <div className="card">
              <div className="card-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <CheckSquare size={16} color="#16a34a" />
                  <span className="card-title">{selectedCase.title}</span>
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
                  <div style={{ marginBottom: '16px' }}>
                    <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '4px' }}>
                      Preconditions
                    </div>
                    <div style={{ fontSize: '13px', color: '#334155', background: '#f8fafc', padding: '8px 12px', borderRadius: '4px' }}>
                      {selectedCase.preconditions}
                    </div>
                  </div>
                )}

                <div style={{ marginBottom: '16px' }}>
                  <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
                    Test Steps ({selectedCase.steps.length})
                  </div>
                  {selectedCase.steps.length > 0 ? (
                    <ol style={{ paddingLeft: '20px', fontSize: '13px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
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

                <div style={{ marginBottom: '16px' }}>
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
          ) : (
            <div className="card">
              <div className="card-body" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
                Select a test case to view step details.
              </div>
            </div>
          )}
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
