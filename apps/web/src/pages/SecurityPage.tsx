import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation('security');
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
          <h2>{t('titles:security')}</h2>
          <p className="subtitle">{t('subtitle')}</p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          {activeTab === 'users' && (
            <button className="btn btn-primary" onClick={() => setShowCreateUserModal(true)}>
              <Plus size={14} />
              <span>{t('addUser')}</span>
            </button>
          )}
          {activeTab === 'teams' && (
            <button className="btn btn-primary" onClick={() => setShowCreateTeamModal(true)}>
              <Plus size={14} />
              <span>{t('createTeam')}</span>
            </button>
          )}
          {activeTab === 'keys' && (
            <button className="btn btn-primary" onClick={() => setShowCreateKeyModal(true)}>
              <Plus size={14} />
              <span>{t('generateApiKey')}</span>
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
            <span>{t('common:refresh')}</span>
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
          {t('tabs.users', { count: users.length })}
        </button>
        <button
          className={`tab-btn ${activeTab === 'teams' ? 'active' : ''}`}
          onClick={() => setActiveTab('teams')}
        >
          <Shield size={15} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
          {t('tabs.teams', { count: teams.length })}
        </button>
        <button
          className={`tab-btn ${activeTab === 'keys' ? 'active' : ''}`}
          onClick={() => setActiveTab('keys')}
        >
          <Key size={15} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
          {t('tabs.keys', { count: apiKeys.length })}
        </button>
        <button
          className={`tab-btn ${activeTab === 'audit' ? 'active' : ''}`}
          onClick={() => setActiveTab('audit')}
        >
          <FileCheck size={15} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
          {t('tabs.audit', { count: auditLogs.length })}
        </button>
      </div>

      {/* Tab 1: Users */}
      {activeTab === 'users' && (
        <div className="card">
          <div className="card-header">
            <h3>{t('users.title')}</h3>
            <span className="text-secondary text-sm">{t('users.subtitle')}</span>
          </div>
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('users.fullName')}</th>
                  <th>{t('users.email')}</th>
                  <th>{t('users.role')}</th>
                  <th>{t('common:status')}</th>
                  <th>{t('users.createdAt')}</th>
                  <th>{t('users.roleChange')}</th>
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
                          <span className="status-pill status-pill-passed">{t('users.active')}</span>
                        ) : (
                          <span className="status-pill status-pill-draft">{t('users.disabled')}</span>
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
                      {loadingUsers ? t('users.loading') : t('users.empty')}
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
            <h3>{t('teams.title')}</h3>
            <span className="text-secondary text-sm">{t('teams.subtitle')}</span>
          </div>
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('teams.name')}</th>
                  <th>{t('common:description')}</th>
                  <th>{t('teams.members')}</th>
                  <th>{t('common:created')}</th>
                </tr>
              </thead>
              <tbody>
                {teams.length > 0 ? (
                  teams.map((team) => (
                    <tr key={team.id}>
                      <td style={{ fontWeight: 600 }}>{team.name}</td>
                      <td>{team.description || '--'}</td>
                      <td>
                        <span className="status-pill status-pill-passed">
                          {t('teams.memberCount', { count: team.member_count })}
                        </span>
                      </td>
                      <td>{new Date(team.created_at).toLocaleDateString()}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} className="text-center text-secondary py-4">
                      {loadingTeams ? t('teams.loading') : t('teams.empty')}
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
            <h3>{t('keys.title')}</h3>
            <span className="text-secondary text-sm">{t('keys.subtitle')}</span>
          </div>
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('keys.name')}</th>
                  <th>{t('keys.prefix')}</th>
                  <th>{t('keys.lastUsed')}</th>
                  <th>{t('common:created')}</th>
                  <th>{t('common:actions')}</th>
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
                      <td>{k.last_used_at ? new Date(k.last_used_at).toLocaleString() : t('keys.never')}</td>
                      <td>{new Date(k.created_at).toLocaleDateString()}</td>
                      <td>
                        <button
                          className="btn btn-secondary btn-sm"
                          style={{ color: 'var(--accent-red)' }}
                          onClick={() => handleDeleteApiKey(k.id)}
                        >
                          <Trash2 size={13} />
                          <span>{t('keys.revoke')}</span>
                        </button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="text-center text-secondary py-4">
                      {loadingKeys ? t('keys.loading') : t('keys.empty')}
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
            <h3>{t('audit.title')}</h3>
            <span className="text-secondary text-sm">{t('audit.subtitle')}</span>
          </div>
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t('audit.timestamp')}</th>
                  <th>{t('audit.action')}</th>
                  <th>{t('audit.actorEmail')}</th>
                  <th>{t('audit.targetResource')}</th>
                  <th>{t('common:status')}</th>
                  <th>{t('audit.ipAddress')}</th>
                  <th>{t('common:details')}</th>
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
                          {t('audit.view')}
                        </button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={7} className="text-center text-secondary py-4">
                      {loadingAudit ? t('audit.loading') : t('audit.empty')}
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
              <h3>{t('users.addTitle')}</h3>
              <button className="btn-icon" onClick={() => setShowCreateUserModal(false)}>
                &times;
              </button>
            </div>
            <form onSubmit={handleCreateUser}>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div className="form-group">
                  <label>{t('users.fullNameLabel')}</label>
                  <input
                    type="text"
                    className="form-control"
                    required
                    placeholder={t('users.fullNamePlaceholder')}
                    value={newUserFullName}
                    onChange={(e) => setNewUserFullName(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>{t('users.emailLabel')}</label>
                  <input
                    type="email"
                    className="form-control"
                    required
                    placeholder={t('users.emailPlaceholder')}
                    value={newUserEmail}
                    onChange={(e) => setNewUserEmail(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>{t('users.roleLabel')}</label>
                  <select
                    className="form-control"
                    value={newUserRole}
                    onChange={(e) => setNewUserRole(e.target.value as UserRole)}
                  >
                    <option value="QA_ENGINEER">{t('users.roleQaEngineer')}</option>
                    <option value="QA_LEAD">{t('users.roleQaLead')}</option>
                    <option value="ADMIN">{t('users.roleAdmin')}</option>
                    <option value="VIEWER">{t('users.roleViewer')}</option>
                  </select>
                </div>
              </div>
              <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowCreateUserModal(false)}>
                  {t('common:cancel')}
                </button>
                <button type="submit" className="btn btn-primary" disabled={creatingUser}>
                  {creatingUser ? t('creating') : t('users.create')}
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
              <h3>{t('teams.createTitle')}</h3>
              <button className="btn-icon" onClick={() => setShowCreateTeamModal(false)}>
                &times;
              </button>
            </div>
            <form onSubmit={handleCreateTeam}>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div className="form-group">
                  <label>{t('teams.nameLabel')}</label>
                  <input
                    type="text"
                    className="form-control"
                    required
                    placeholder={t('teams.namePlaceholder')}
                    value={newTeamName}
                    onChange={(e) => setNewTeamName(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>{t('common:description')}</label>
                  <textarea
                    className="form-control"
                    rows={3}
                    placeholder={t('teams.descriptionPlaceholder')}
                    value={newTeamDescription}
                    onChange={(e) => setNewTeamDescription(e.target.value)}
                  />
                </div>
              </div>
              <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowCreateTeamModal(false)}>
                  {t('common:cancel')}
                </button>
                <button type="submit" className="btn btn-primary" disabled={creatingTeam}>
                  {creatingTeam ? t('creating') : t('createTeam')}
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
              <h3>{t('keys.generateTitle')}</h3>
              <button className="btn-icon" onClick={() => setShowCreateKeyModal(false)}>
                &times;
              </button>
            </div>
            <form onSubmit={handleCreateApiKey}>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div className="form-group">
                  <label>{t('keys.nameLabel')}</label>
                  <input
                    type="text"
                    className="form-control"
                    required
                    placeholder={t('keys.namePlaceholder')}
                    value={newKeyName}
                    onChange={(e) => setNewKeyName(e.target.value)}
                  />
                </div>
              </div>
              <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowCreateKeyModal(false)}>
                  {t('common:cancel')}
                </button>
                <button type="submit" className="btn btn-primary" disabled={creatingKey}>
                  {creatingKey ? t('generating') : t('keys.generate')}
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
                <Key size={18} color="var(--accent-green)" />
                <h3>{t('keys.generatedTitle')}</h3>
              </div>
              <button className="btn-icon" onClick={() => setGeneratedKeyResult(null)}>
                &times;
              </button>
            </div>
            <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <p style={{ fontSize: '0.9rem', color: 'var(--accent-amber)' }}>{t('keys.generatedWarning')}</p>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  backgroundColor: 'var(--bg-subtle)',
                  padding: '10px',
                  borderRadius: 'var(--r-xs)',
                  border: '1px solid var(--border-color)',
                }}
              >
                <code style={{ fontSize: '0.85rem', wordBreak: 'break-all', flex: 1 }}>
                  {generatedKeyResult.raw_api_key}
                </code>
                <button className="btn btn-secondary btn-sm" onClick={handleCopyKey}>
                  {copiedKey ? <Check size={14} color="var(--accent-green)" /> : <Copy size={14} />}
                  <span>{copiedKey ? t('common:copied') : t('common:copy')}</span>
                </button>
              </div>
            </div>
            <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button className="btn btn-primary" onClick={() => setGeneratedKeyResult(null)}>
                {t('keys.done')}
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
              <h3>{t('audit.detailsTitle')}</h3>
              <button className="btn-icon" onClick={() => setSelectedAuditLog(null)}>
                &times;
              </button>
            </div>
            <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div>
                <strong>{t('audit.actionLabel')}</strong> {selectedAuditLog.action}
              </div>
              <div>
                <strong>{t('audit.actorLabel')}</strong> {selectedAuditLog.actor_email} ({selectedAuditLog.actor_id})
              </div>
              <div>
                <strong>{t('audit.targetLabel')}</strong> <code>{selectedAuditLog.target_resource}</code>
              </div>
              <div>
                <strong>{t('audit.statusLabel')}</strong> {selectedAuditLog.status}
              </div>
              <div>
                <strong>{t('audit.ipLabel')}</strong> {selectedAuditLog.ip_address}
              </div>
              <div>
                <strong>{t('audit.payloadLabel')}</strong>
                <pre
                  style={{
                    backgroundColor: 'var(--bg-subtle)',
                    padding: '8px',
                    borderRadius: 'var(--r-xs)',
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
                {t('common:close')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
