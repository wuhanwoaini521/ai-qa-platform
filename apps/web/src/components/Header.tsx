import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  ChevronLeft,
  ChevronRight,
  Sparkles,
  Cpu,
  Globe,
  LogOut,
  X,
} from 'lucide-react';
import { AIStatusResponse, RunnerProfile } from '../types';
import { api } from '../api/client';
import { SUPPORTED_LANGUAGES } from '../i18n';
import { usePreferences } from '../app/Preferences';

interface HeaderProps {
  title: string;
  selectedProjectId: string | null;
  onSignOut: () => void;
}

/**
 * Toolbar: optional page context and one system-status trigger. Everything infrequent (AI
 * provider, runners, language, sign out) lives in the status panel to keep the bar quiet.
 */
export const Header: React.FC<HeaderProps> = ({
  title,
  selectedProjectId,
  onSignOut,
}) => {
  const { t } = useTranslation('common');
  const navigate = useNavigate();
  const { language, setLanguage } = usePreferences();
  const [aiStatus, setAiStatus] = useState<AIStatusResponse | null>(null);
  const [runnerProfiles, setRunnerProfiles] = useState<RunnerProfile[]>([]);
  const [panelOpen, setPanelOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const [ai, runners] = await Promise.allSettled([
          api.getAIStatus(),
          api.getRunnerProfiles(selectedProjectId || undefined),
        ]);
        if (ai.status === 'fulfilled') setAiStatus(ai.value);
        if (runners.status === 'fulfilled') setRunnerProfiles(runners.value);
      } catch (err) {
        console.error('Failed to load status in header', err);
      }
    };
    fetchStatus();
  }, [selectedProjectId]);

  useEffect(() => {
    if (!panelOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(event.target as Node)) {
        setPanelOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setPanelOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [panelOpen]);

  const aiState =
    aiStatus?.operational_state === 'READY'
      ? 'ok'
      : aiStatus?.operational_state === 'UNAVAILABLE'
        || aiStatus?.operational_state === 'UNCONFIGURED'
        || aiStatus?.operational_state === 'DISABLED'
        ? 'bad'
        : 'warn';

  return (
    <header className="app-topbar">
      <div className="topbar-title-section">
        <div className="topbar-nav">
          <button type="button" onClick={() => navigate(-1)} aria-label={t('back')} title={t('back')}>
            <ChevronLeft size={17} strokeWidth={1.6} />
          </button>
          <button type="button" onClick={() => navigate(1)} aria-label={t('next')} title={t('next')}>
            <ChevronRight size={17} strokeWidth={1.6} />
          </button>
        </div>

        <span className="topbar-separator" aria-hidden="true" />

        <h1 className="topbar-page-title">{title}</h1>
      </div>

      <div className="topbar-utility-section">
        <div className="topbar-status" ref={panelRef}>
          <button
            type="button"
            className="topbar-status-trigger"
            aria-haspopup="dialog"
            aria-expanded={panelOpen}
            onClick={() => setPanelOpen((open) => !open)}
          >
            <span className={`status-dot is-${aiState === 'ok' ? 'online' : aiState === 'bad' ? 'failed' : 'queued'}`} />
            <span className="topbar-status-text">{t('systemStatus')}</span>
          </button>

          {panelOpen && (
            <div className="topbar-status-panel" role="dialog" aria-label={t('systemStatus')}>
              <div className="topbar-status-head">
                <span>{t('systemStatus')}</span>
                <button
                  type="button"
                  className="icon-btn"
                  aria-label={t('close')}
                  onClick={() => setPanelOpen(false)}
                >
                  <X size={14} strokeWidth={1.6} />
                </button>
              </div>

              <dl className="topbar-status-list">
                <div className="topbar-status-item">
                  <dt>
                    <Sparkles size={14} strokeWidth={1.7} />
                    {t('aiProvider')}
                  </dt>
                  <dd>
                    {aiStatus ? `${aiStatus.provider} · ${aiStatus.operational_state}` : t('unknown')}
                  </dd>
                </div>
                <div className="topbar-status-item">
                  <dt>
                    <Cpu size={14} strokeWidth={1.7} />
                    {t('runners')}
                  </dt>
                  <dd>{runnerProfiles.length > 0 ? runnerProfiles.length : t('local')}</dd>
                </div>
                <div className="topbar-status-item">
                  <dt>
                    <Globe size={14} strokeWidth={1.7} />
                    {t('language')}
                  </dt>
                  <dd>
                    <select
                      className="topbar-status-select"
                      aria-label={t('language')}
                      value={language}
                      onChange={(e) =>
                        setLanguage(
                          e.target.value as (typeof SUPPORTED_LANGUAGES)[number]['code'],
                        )
                      }
                    >
                      {SUPPORTED_LANGUAGES.map((entry) => (
                        <option key={entry.code} value={entry.code}>
                          {entry.label}
                        </option>
                      ))}
                    </select>
                  </dd>
                </div>
              </dl>

              <button type="button" className="topbar-signout" onClick={onSignOut}>
                <LogOut size={14} strokeWidth={1.7} />
                {t('signOut')}
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};