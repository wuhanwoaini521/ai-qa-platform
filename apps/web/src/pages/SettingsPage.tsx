import React from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Globe, LayoutDashboard, RotateCcw } from 'lucide-react';
import { SUPPORTED_LANGUAGES } from '../i18n';
import { START_PAGE_OPTIONS, usePreferences } from '../app/Preferences';
import { useProjectScope } from '../app/ProjectScope';

/** Settings page: language, start page and default project. Everything here is wired to real behaviour. */
export const SettingsPage: React.FC = () => {
  const { t } = useTranslation('settings');
  const { language, setLanguage, startPage, setStartPage, defaultProjectId, setDefaultProjectId, reset } =
    usePreferences();
  const { projects } = useProjectScope();

  return (
    <div style={{ padding: '20px', maxWidth: '720px' }}>
      <div className="card" style={{ marginBottom: '16px' }}>
        <div className="card-header">
          <span className="card-title">{t('title')}</span>
        </div>
        <div className="card-body">
          <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '16px' }}>
            {t('subtitle')}
          </p>

          {/* Language */}
          <div style={{ marginBottom: '20px' }}>
            <label className="form-label" htmlFor="settings-language">
              <Globe size={13} style={{ verticalAlign: '-2px', marginRight: '6px' }} />
              {t('common:language')}
            </label>
            <select
              id="settings-language"
              className="form-control"
              style={{ maxWidth: '280px' }}
              value={language}
              onChange={(e) => setLanguage(e.target.value as (typeof SUPPORTED_LANGUAGES)[number]['code'])}
            >
              {SUPPORTED_LANGUAGES.map((entry) => (
                <option key={entry.code} value={entry.code}>
                  {entry.label}
                </option>
              ))}
            </select>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
              {t('common:languageDescription')}
            </div>
          </div>

          {/* Start page */}
          <div style={{ marginBottom: '20px' }}>
            <label className="form-label" htmlFor="settings-start-page">
              <LayoutDashboard size={13} style={{ verticalAlign: '-2px', marginRight: '6px' }} />
              {t('startPage')}
            </label>
            <select
              id="settings-start-page"
              className="form-control"
              style={{ maxWidth: '280px' }}
              value={startPage}
              onChange={(e) => setStartPage(e.target.value)}
            >
              {START_PAGE_OPTIONS.map((option) => (
                <option key={option.path} value={option.path}>
                  {t(option.labelKey)}
                </option>
              ))}
            </select>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
              {t('startPageDescription')}
            </div>
          </div>

          {/* Default project */}
          <div>
            <label className="form-label" htmlFor="settings-default-project">
              {t('defaultProject')}
            </label>
            <select
              id="settings-default-project"
              className="form-control"
              style={{ maxWidth: '280px' }}
              value={defaultProjectId ?? ''}
              onChange={(e) => setDefaultProjectId(e.target.value || null)}
            >
              <option value="">{t('defaultProjectNone')}</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
              {t('defaultProjectDescription')}
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '20px' }}>
            <span style={{ fontSize: '12px', color: 'var(--success-color, #16a34a)' }}>
              <Check size={13} style={{ verticalAlign: '-2px', marginRight: '4px' }} />
              {t('saved')}
            </span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={reset}>
              <RotateCcw size={13} /> {t('common:reset')}
            </button>
          </div>

          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '12px' }}>{t('storageNote')}</div>
        </div>
      </div>
    </div>
  );
};
