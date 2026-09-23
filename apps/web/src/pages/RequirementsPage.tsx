import React, { useEffect, useState } from 'react';
import { Project, Requirement, RequirementCreate, RequirementStatus, TestDesign, TestDesignCategory, TestDesignCreate } from '../types';
import { api } from '../api/client';
import { Plus, FileText, Layers, ChevronRight } from 'lucide-react';

interface RequirementsPageProps {
  projects: Project[];
  selectedProjectId: string | null;
}

export const RequirementsPage: React.FC<RequirementsPageProps> = ({ projects, selectedProjectId }) => {
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedReq, setSelectedReq] = useState<Requirement | null>(null);
  const [testDesigns, setTestDesigns] = useState<TestDesign[]>([]);

  // Modals
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
          <h2 style={{ fontSize: '18px', fontWeight: 700 }}>Requirement & Test Design</h2>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            Map business requirements and user stories to structured QA test designs.
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
                            <span className={`badge badge-${r.status.toLowerCase()}`}>{r.status}</span>
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
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <select
                      className="form-control"
                      style={{ padding: '3px 8px', fontSize: '12px', width: '120px' }}
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
                        fontFamily: 'var(--font-mono)',
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
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => {
                      setDesignFormData({ ...designFormData, requirement_id: selectedReq.id });
                      setIsDesignModalOpen(true);
                    }}
                  >
                    <Plus size={13} /> Add Test Design
                  </button>
                </div>
                <div className="card-body" style={{ padding: 0 }}>
                  {testDesigns.length === 0 ? (
                    <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
                      No test designs yet. Break down this requirement into functional, boundary, or negative designs.
                    </div>
                  ) : (
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Design Title</th>
                          <th>Category</th>
                          <th>Risk</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {testDesigns.map((td) => (
                          <tr key={td.id}>
                            <td style={{ fontWeight: 500 }}>{td.title}</td>
                            <td>
                              <span className="badge badge-draft">{td.category}</span>
                            </td>
                            <td>{td.risk}</td>
                            <td>
                              <span className="badge badge-ready">{td.status}</span>
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

      {/* Create Requirement Modal */}
      {isReqModalOpen && (
        <div className="modal-overlay">
          <div className="modal-dialog">
            <form onSubmit={handleCreateRequirement}>
              <div className="modal-header">
                <h3 style={{ fontSize: '15px', fontWeight: 700 }}>New Requirement</h3>
                <button
                  type="button"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '16px' }}
                  onClick={() => setIsReqModalOpen(false)}
                >
                  ✕
                </button>
              </div>
              <div className="modal-body" style={{ padding: '20px' }}>
                <div className="form-group">
                  <label className="form-label">Project *</label>
                  <select
                    className="form-control"
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
                    className="form-control"
                    placeholder="e.g. User Authentication & Password Reset"
                    value={reqFormData.title}
                    onChange={(e) => setReqFormData({ ...reqFormData, title: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Description</label>
                  <textarea
                    rows={3}
                    className="form-control"
                    placeholder="Detailed explanation of the feature or requirement..."
                    value={reqFormData.description}
                    onChange={(e) => setReqFormData({ ...reqFormData, description: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Acceptance Criteria</label>
                  <textarea
                    rows={3}
                    className="form-control"
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
                    className="form-control"
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
          <div className="modal-dialog">
            <form onSubmit={handleCreateTestDesign}>
              <div className="modal-header">
                <h3 style={{ fontSize: '15px', fontWeight: 700 }}>Add Test Design</h3>
                <button
                  type="button"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '16px' }}
                  onClick={() => setIsDesignModalOpen(false)}
                >
                  ✕
                </button>
              </div>
              <div className="modal-body" style={{ padding: '20px' }}>
                <div className="form-group">
                  <label className="form-label">Design Title *</label>
                  <input
                    type="text"
                    required
                    className="form-control"
                    placeholder="e.g. Boundary Test: Negative Input Handling"
                    value={designFormData.title}
                    onChange={(e) => setDesignFormData({ ...designFormData, title: e.target.value })}
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div className="form-group">
                    <label className="form-label">Category</label>
                    <select
                      className="form-control"
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
                      className="form-control"
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
                    className="form-control"
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
