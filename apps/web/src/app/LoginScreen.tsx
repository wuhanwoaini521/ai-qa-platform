import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, setAuthToken } from '../api/client';
import { LoginResponse } from '../types';

interface LoginScreenProps {
  onAuthenticated: (session: LoginResponse) => void;
}

export const LoginScreen: React.FC<LoginScreenProps> = ({ onAuthenticated }) => {
  const { t } = useTranslation('auth');
  const [email, setEmail] = useState<string>('admin@ai-qa.local');
  const [password, setPassword] = useState<string>('');
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const session = await api.login(email, password);
      setAuthToken(session.access_token);
      onAuthenticated(session);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('failed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'var(--bg-app, #0b1120)',
      }}
    >
      <form
        className="card"
        style={{ width: '360px', padding: '28px' }}
        onSubmit={handleSubmit}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
          <div className="sidebar-logo-icon">QA</div>
          <div className="sidebar-brand-title">{t('common:appName')}</div>
        </div>

        <label className="form-label" htmlFor="login-email">
          {t('email')}
        </label>
        <input
          id="login-email"
          className="form-control"
          style={{ width: '100%', marginBottom: '12px' }}
          value={email}
          autoComplete="username"
          onChange={(e) => setEmail(e.target.value)}
        />

        <label className="form-label" htmlFor="login-password">
          {t('password')}
        </label>
        <input
          id="login-password"
          className="form-control"
          type="password"
          style={{ width: '100%', marginBottom: '16px' }}
          value={password}
          autoComplete="current-password"
          onChange={(e) => setPassword(e.target.value)}
        />

        {error && (
          <div style={{ color: '#ef4444', fontSize: '12px', marginBottom: '12px' }} role="alert">
            {error}
          </div>
        )}

        <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={submitting}>
          {submitting ? t('submitting') : t('submit')}
        </button>

        <div style={{ marginTop: '14px', fontSize: '11px', color: 'var(--text-muted)' }}>{t('hint')}</div>
      </form>
    </div>
  );
};
