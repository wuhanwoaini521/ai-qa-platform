import React, { useEffect, useState } from 'react';
import {
  Users,
  Shield,
  Key,
  FileCheck,
  Plus,
  RefreshCw,
  Trash2,
  Copy,
  Check,
} from 'lucide-react';
import {
  ApiKey,
  ApiKeyCreatedResponse,
  SecurityAuditLogEntry,
  Team,
  User,
  UserRole,
} from '../types';
import { api } from '../api/client';

export const SecurityPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'users' | 'teams' | 'keys' | 'audit'>('users');

  // Users State
  const [users, setUsers] = useState<User[]>([]);
  const [loadingUsers, setLoadingUsers] = useState<boolean>(true);
  const [showCreateUserModal, setShowCreateUserModal] = useState<boolean>(false);
  const [newUserEmail, setNewUserEmail] = useState<string>('');
  const [newUserFullName, setNewUserFullName] = useState<string>('');
  const [newUserRole, setNewUserRole] = useState<UserRole>('QA_ENGINEER');
  const [creatingUser, setCreatingUser] = useState<boolean>(false);

  // Teams State
  const [teams, setTeams] = useState<Team[]>([]);
  const [loadingTeams, setLoadingTeams] = useState<boolean>(false);
  const [showCreateTeamModal, setShowCreateTeamModal] = useState<boolean>(false);
  const [newTeamName, setNewTeamName] = useState<string>('');
  const [newTeamDescription, setNewTeamDescription] = useState<string>('');
  const [creatingTeam, setCreatingTeam] = useState<boolean>(false);

  // API Keys State
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [loadingKeys, setLoadingKeys] = useState<boolean>(false);
  const [showCreateKeyModal, setShowCreateKeyModal] = useState<boolean>(false);
  const [newKeyName, setNewKeyName] = useState<string>('');
  const [creatingKey, setCreatingKey] = useState<boolean>(false);
  const [generatedKeyResult, setGeneratedKeyResult] = useState<ApiKeyCreatedResponse | null>(null);
  const [copiedKey, setCopiedKey] = useState<boolean>(false);

  // Security Audit State
  const [auditLogs, setAuditLogs] = useState<SecurityAuditLogEntry[]>([]);
  const [loadingAudit, setLoadingAudit] = useState<boolean>(false);
  const [selectedAuditLog, setSelectedAuditLog] = useState<SecurityAuditLogEntry | null>(null);

  const fetchUsers = async () => {
    try {
      setLoadingUsers(true);
      const data = await api.getUsers();
      setUsers(data);
    } catch (err) {
      console.error('Failed to load users', err);
    } finally {
      setLoadingUsers(false);
    }
  };

  const fetchTeams = async () => {
    try {
      setLoadingTeams(true);
      const data = await api.getTeams();
      setTeams(data);
    } catch (err) {
      console.error('Failed to load teams', err);
    } finally {
      setLoadingTeams(false);
    }
  };

  const fetchApiKeys = async () => {
    try {
      setLoadingKeys(true);
      const data = await api.getApiKeys();
      setApiKeys(data);
    } catch (err) {
      console.error('Failed to load API keys', err);
    } finally {
      setLoadingKeys(false);
    }
  };

  const fetchSecurityAudits = async () => {
    try {
      setLoadingAudit(true);
      const data = await api.getSecurityAudits();
      setAuditLogs(data);
    } catch (err) {
      console.error('Failed to load security audit logs', err);
    } finally {
      setLoadingAudit(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'users') fetchUsers();
    if (activeTab === 'teams') fetchTeams();
    if (activeTab === 'keys') fetchApiKeys();
    if (activeTab === 'audit') fetchSecurityAudits();
  }, [activeTab]);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUserEmail || !newUserFullName) return;
    try {
      setCreatingUser(true);
      const created = await api.createUser({
        email: newUserEmail,
        full_name: newUserFullName,
        role: newUserRole,
      });
      setUsers([created, ...users]);
      setShowCreateUserModal(false);
      setNewUserEmail('');
      setNewUserFullName('');
      setNewUserRole('QA_ENGINEER');
    } catch (err) {
      console.error('Failed to create user', err);
    } finally {
      setCreatingUser(false);
    }
  };

  const handleRoleChange = async (userId: string, newRole: UserRole) => {
    try {
      const updated = await api.updateUser(userId, { role: newRole });
      setUsers(users.map((u) => (u.id === userId ? updated : u)));
    } catch (err) {
      console.error('Failed to update role', err);
    }
  };

  const handleCreateTeam = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTeamName) return;
    try {
      setCreatingTeam(true);
      const created = await api.createTeam({
        name: newTeamName,
        description: newTeamDescription,
      });
      setTeams([created, ...teams]);
      setShowCreateTeamModal(false);
      setNewTeamName('');
      setNewTeamDescription('');
    } catch (err) {
      console.error('Failed to create team', err);
    } finally {
      setCreatingTeam(false);
    }
  };

  const handleCreateApiKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newKeyName) return;
    try {
      setCreatingKey(true);
      const res = await api.createApiKey({ name: newKeyName });
      setGeneratedKeyResult(res);
      setApiKeys([res, ...apiKeys]);
      setNewKeyName('');
      setShowCreateKeyModal(false);
    } catch (err) {
      console.error('Failed to generate API key', err);
    } finally {
      setCreatingKey(false);
    }
  };

  const handleDeleteApiKey = async (keyId: string) => {
    try {
      await api.deleteApiKey(keyId);
      setApiKeys(apiKeys.filter((k) => k.id !== keyId));
    } catch (err) {
      console.error('Failed to revoke key', err);
    }
  };

  const handleCopyKey = () => {
    if (generatedKeyResult?.raw_api_key) {
      navigator.clipboard.writeText(generatedKeyResult.raw_api_key);
      setCopiedKey(true);
      setTimeout(() => setCopiedKey(false), 2000);
    }
  };

  const getRoleBadge = (role: UserRole) => {
    switch (role) {
      case 'ADMIN':
        return <span className="status-pill status-pill-error">ADMIN</span>;
      case 'QA_LEAD':
        return <span className="status-pill status-pill-warning">QA LEAD</span>;
      case 'QA_ENGINEER':
        return <span className="status-pill status-pill-passed">QA ENGINEER</span>;
      case 'VIEWER':
      default:
        return <span className="status-pill status-pill-draft">VIEWER</span>;
    }
  };

  return (
    <div className="page-container">
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h2>Enterprise Security & RBAC</h2>
          <p className="subtitle">
            User directory, capability-based access control, service API keys, and immutable security audit trails.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          {activeTab === 'users' && (
            <button className="btn btn-primary" onClick={() => setShowCreateUserModal(true)}>
              <Plus size={14} />
              <span>Add User</span>
            </button>
          )}
          {activeTab === 'teams' && (
            <button className="btn btn-primary" onClick={() => setShowCreateTeamModal(true)}>
              <Plus size={14} />
              <span>Create Team</span>
            </button>
          )}
          {activeTab === 'keys' && (
            <button className="btn btn-primary" onClick={() => setShowCreateKeyModal(true)}>
              <Plus size={14} />
              <span>Generate API Key</span>
            </button>
          )}
          <button
            className="btn btn-secondary"
            onClick={() => {
              if (activeTab === 'users') fetchUsers();
              if (activeTab === 'teams') fetchTeams();
              if (activeTab === 'keys') fetchApiKeys();
              if (activeTab === 'audit') fetchSecurityAudits();
            }}
          >
            <RefreshCw size={14} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="tabs-container" style={{ marginBottom: '1.5rem' }}>
        <button
          className={`tab-btn ${activeTab === 'users' ? 'active' : ''}`}
          onClick={() => setActiveTab('users')}
        >
          <Users size={15} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
          Users & Roles ({users.length})
        </button>
        <button
          className={`tab-btn ${activeTab === 'teams' ? 'active' : ''}`}
          onClick={() => setActiveTab('teams')}
        >
          <Shield size={15} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
          Teams & Squads ({teams.length})
        </button>
        <button
          className={`tab-btn ${activeTab === 'keys' ? 'active' : ''}`}
          onClick={() => setActiveTab('keys')}
        >
          <Key size={15} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
          API Keys ({apiKeys.length})
        </button>
        <button
          className={`tab-btn ${activeTab === 'audit' ? 'active' : ''}`}
          onClick={() => setActiveTab('audit')}
        >
          <FileCheck size={15} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
          Security Audit Trail ({auditLogs.length})
        </button>
      </div>

      {/* Tab 1: Users */}
      {activeTab === 'users' && (
        <div className="card">
          <div className="card-header">
            <h3>Enterprise Users & Permissions</h3>
            <span className="text-secondary text-sm">
              Role permissions dictate access to test creation, automation runs, and release gate authorizations.
            </span>
          </div>
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Full Name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Created At</th>
                  <th>Role Change</th>
                </tr>
              </thead>
              <tbody>
                {users.length > 0 ? (
                  users.map((u) => (
                    <tr key={u.id}>
                      <td style={{ fontWeight: 600 }}>{u.full_name}</td>
                      <td>{u.email}</td>
                      <td>{getRoleBadge(u.role)}</td>
                      <td>
                        {u.is_active ? (
                          <span className="status-pill status-pill-passed">Active</span>
                        ) : (
                          <span className="status-pill status-pill-draft">Disabled</span>
                        )}
                      </td>
                      <td>{new Date(u.created_at).toLocaleDateString()}</td>
                      <td>
                        <select
                          className="form-control"
                          style={{ padding: '4px 8px', fontSize: '0.85rem', width: 'auto' }}
                          value={u.role}
                          onChange={(e) => handleRoleChange(u.id, e.target.value as UserRole)}
                        >
                          <option value="ADMIN">ADMIN</option>
                          <option value="QA_LEAD">QA LEAD</option>
                          <option value="QA_ENGINEER">QA ENGINEER</option>
                          <option value="VIEWER">VIEWER</option>
                        </select>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6} className="text-center text-secondary py-4">
                      {loadingUsers ? 'Loading users...' : 'No users found.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 2: Teams */}
      {activeTab === 'teams' && (
        <div className="card">
          <div className="card-header">
            <h3>QA Teams & Squads</h3>
            <span className="text-secondary text-sm">
              Organize QA engineers and test case ownership across domains.
            </span>
          </div>
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Team Name</th>
                  <th>Description</th>
                  <th>Members</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {teams.length > 0 ? (
                  teams.map((t) => (
                    <tr key={t.id}>
                      <td style={{ fontWeight: 600 }}>{t.name}</td>
                      <td>{t.description || '--'}</td>
                      <td>
                        <span className="status-pill status-pill-passed">{t.member_count} members</span>
                      </td>
                      <td>{new Date(t.created_at).toLocaleDateString()}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} className="text-center text-secondary py-4">
                      {loadingTeams ? 'Loading teams...' : 'No teams configured. Click "Create Team" to add one.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 3: API Keys */}
      {activeTab === 'keys' && (
        <div className="card">
          <div className="card-header">
            <h3>Service & CI/CD API Keys</h3>
            <span className="text-secondary text-sm">
              Authenticate Jenkins runners, GitHub Actions workflows, and external pipelines.
            </span>
          </div>
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Key Name</th>
                  <th>Key Prefix</th>
                  <th>Last Used</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {apiKeys.length > 0 ? (
                  apiKeys.map((k) => (
                    <tr key={k.id}>
                      <td style={{ fontWeight: 600 }}>{k.name}</td>
                      <td>
                        <code>{k.key_prefix}••••••••</code>
                      </td>
                      <td>{k.last_used_at ? new Date(k.last_used_at).toLocaleString() : 'Never'}</td>
                      <td>{new Date(k.created_at).toLocaleDateString()}</td>
                      <td>
                        <button
                          className="btn btn-secondary btn-sm"
                          style={{ color: '#ef4444' }}
                          onClick={() => handleDeleteApiKey(k.id)}
                        >
                          <Trash2 size={13} />
                          <span>Revoke</span>
                        </button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="text-center text-secondary py-4">
                      {loadingKeys ? 'Loading API keys...' : 'No API keys generated.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 4: Security Audit Trail */}
      {activeTab === 'audit' && (
        <div className="card">
          <div className="card-header">
            <h3>Immutable Security Audit Trail</h3>
            <span className="text-secondary text-sm">
              Tamper-evident logs of logins, role updates, API key generations, and release gate actions.
            </span>
          </div>
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Action</th>
                  <th>Actor Email</th>
                  <th>Target Resource</th>
                  <th>Status</th>
                  <th>IP Address</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {auditLogs.length > 0 ? (
                  auditLogs.map((log) => (
                    <tr key={log.id}>
                      <td style={{ fontSize: '0.85rem' }}>{new Date(log.created_at).toLocaleString()}</td>
                      <td>
                        <span className="status-pill status-pill-draft">{log.action}</span>
                      </td>
                      <td>{log.actor_email}</td>
                      <td>
                        <code>{log.target_resource}</code>
                      </td>
                      <td>
                        <span
                          className={`status-pill ${
                            log.status === 'SUCCESS'
                              ? 'status-pill-passed'
                              : log.status === 'DENIED'
                              ? 'status-pill-failed'
                              : 'status-pill-error'
                          }`}
                        >
                          {log.status}
                        </span>
                      </td>
                      <td>{log.ip_address}</td>
                      <td>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => setSelectedAuditLog(log)}
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={7} className="text-center text-secondary py-4">
                      {loadingAudit ? 'Loading security audit logs...' : 'No security audit entries recorded.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Modal: Create User */}
      {showCreateUserModal && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '480px' }}>
            <div className="modal-header">
              <h3>Add New User</h3>
              <button className="btn-icon" onClick={() => setShowCreateUserModal(false)}>
                &times;
              </button>
            </div>
            <form onSubmit={handleCreateUser}>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div className="form-group">
                  <label>Full Name *</label>
                  <input
                    type="text"
                    className="form-control"
                    required
                    placeholder="Jane Doe"
                    value={newUserFullName}
                    onChange={(e) => setNewUserFullName(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>Email Address *</label>
                  <input
                    type="email"
                    className="form-control"
                    required
                    placeholder="jane@company.com"
                    value={newUserEmail}
                    onChange={(e) => setNewUserEmail(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>Role Assignment *</label>
                  <select
                    className="form-control"
                    value={newUserRole}
                    onChange={(e) => setNewUserRole(e.target.value as UserRole)}
                  >
                    <option value="QA_ENGINEER">QA ENGINEER (Author & Execute)</option>
                    <option value="QA_LEAD">QA LEAD (Manage & Release Gate)</option>
                    <option value="ADMIN">ADMIN (Full Platform Control)</option>
                    <option value="VIEWER">VIEWER (Read-Only)</option>
                  </select>
                </div>
              </div>
              <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowCreateUserModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={creatingUser}>
                  {creatingUser ? 'Creating...' : 'Create User'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Create Team */}
      {showCreateTeamModal && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '480px' }}>
            <div className="modal-header">
              <h3>Create QA Team</h3>
              <button className="btn-icon" onClick={() => setShowCreateTeamModal(false)}>
                &times;
              </button>
            </div>
            <form onSubmit={handleCreateTeam}>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div className="form-group">
                  <label>Team Name *</label>
                  <input
                    type="text"
                    className="form-control"
                    required
                    placeholder="Payments QA Squad"
                    value={newTeamName}
                    onChange={(e) => setNewTeamName(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>Description</label>
                  <textarea
                    className="form-control"
                    rows={3}
                    placeholder="Responsible for checkout and payment gateway test automation."
                    value={newTeamDescription}
                    onChange={(e) => setNewTeamDescription(e.target.value)}
                  />
                </div>
              </div>
              <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowCreateTeamModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={creatingTeam}>
                  {creatingTeam ? 'Creating...' : 'Create Team'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Generate API Key */}
      {showCreateKeyModal && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '480px' }}>
            <div className="modal-header">
              <h3>Generate Service API Key</h3>
              <button className="btn-icon" onClick={() => setShowCreateKeyModal(false)}>
                &times;
              </button>
            </div>
            <form onSubmit={handleCreateApiKey}>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div className="form-group">
                  <label>Key Description / Name *</label>
                  <input
                    type="text"
                    className="form-control"
                    required
                    placeholder="GitHub Actions CI Runner"
                    value={newKeyName}
                    onChange={(e) => setNewKeyName(e.target.value)}
                  />
                </div>
              </div>
              <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowCreateKeyModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={creatingKey}>
                  {creatingKey ? 'Generating...' : 'Generate Key'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Display Generated Raw API Key */}
      {generatedKeyResult && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '540px' }}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Key size={18} color="#10b981" />
                <h3>API Key Generated Successfully</h3>
              </div>
              <button className="btn-icon" onClick={() => setGeneratedKeyResult(null)}>
                &times;
              </button>
            </div>
            <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <p style={{ fontSize: '0.9rem', color: '#f59e0b' }}>
                Please copy your API key now. You will not be able to view it again!
              </p>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  backgroundColor: 'var(--bg-subtle)',
                  padding: '10px',
                  borderRadius: '6px',
                  border: '1px solid var(--border-color)',
                }}
              >
                <code style={{ fontSize: '0.85rem', wordBreak: 'break-all', flex: 1 }}>
                  {generatedKeyResult.raw_api_key}
                </code>
                <button className="btn btn-secondary btn-sm" onClick={handleCopyKey}>
                  {copiedKey ? <Check size={14} color="#10b981" /> : <Copy size={14} />}
                  <span>{copiedKey ? 'Copied' : 'Copy'}</span>
                </button>
              </div>
            </div>
            <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button className="btn btn-primary" onClick={() => setGeneratedKeyResult(null)}>
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: View Audit Details */}
      {selectedAuditLog && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '540px' }}>
            <div className="modal-header">
              <h3>Audit Event Details</h3>
              <button className="btn-icon" onClick={() => setSelectedAuditLog(null)}>
                &times;
              </button>
            </div>
            <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div>
                <strong>Action:</strong> {selectedAuditLog.action}
              </div>
              <div>
                <strong>Actor:</strong> {selectedAuditLog.actor_email} ({selectedAuditLog.actor_id})
              </div>
              <div>
                <strong>Target:</strong> <code>{selectedAuditLog.target_resource}</code>
              </div>
              <div>
                <strong>Status:</strong> {selectedAuditLog.status}
              </div>
              <div>
                <strong>IP:</strong> {selectedAuditLog.ip_address}
              </div>
              <div>
                <strong>Payload Details:</strong>
                <pre
                  style={{
                    backgroundColor: 'var(--bg-subtle)',
                    padding: '8px',
                    borderRadius: '6px',
                    fontSize: '0.85rem',
                    overflowX: 'auto',
                    marginTop: '4px',
                  }}
                >
                  {JSON.stringify(selectedAuditLog.details, null, 2)}
                </pre>
              </div>
            </div>
            <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button className="btn btn-primary" onClick={() => setSelectedAuditLog(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
