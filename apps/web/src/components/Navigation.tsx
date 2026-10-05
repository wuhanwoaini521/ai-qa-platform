import React, { useMemo, useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  LayoutDashboard,
  Code2,
  PanelsTopLeft,
  GitBranch,
  BookOpen,
  Flame,
  ShieldCheck,
  Shield,
  Server,
  Settings,
  Search,
  Command,
} from 'lucide-react';
import i18n, { storeLanguage, SUPPORTED_LANGUAGES } from '../i18n';
import { useProjectScope } from '../app/ProjectScope';

export type NavTab =
  | 'dashboard'
  | 'projects'
  | 'requirements'
  | 'test_cases'
  | 'automation'
  | 'recorder'
  | 'runs'
  | 'tasks'
  | 'flaky'
  | 'failures'
  | 'quality'
  | 'security'
  | 'workers'
  | 'settings'
  | 'workspace'
  | 'workflow'
  | 'library';

interface NavItem {
  id: NavTab;
  labelKey: string;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>;
  to: string;
  end?: boolean;
}

const ICON_SIZE = 18;
const ICON_STROKE = 1.6;

/** Navigation rail: brand → search → primary destinations → platform. */
export const Navigation: React.FC = () => {
  const { t } = useTranslation('nav');
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { selectedProjectId } = useProjectScope();
  const [query, setQuery] = useState('');

  const projectBase = selectedProjectId
    ? `/projects/${selectedProjectId}`
    : null;

  const navItems: NavItem[] = [
    { id: 'dashboard', labelKey: 'dashboard', icon: LayoutDashboard, to: '/', end: true },
    { id: 'workspace', labelKey: 'workspace', icon: PanelsTopLeft, to: projectBase ? `/workspace/${selectedProjectId}` : '/workspace' },
    {
      id: 'automation',
      labelKey: 'automation',
      icon: Code2,
      to: projectBase ? `${projectBase}/studio` : '/projects',
    },
    { id: 'workflow', labelKey: 'workflow', icon: GitBranch, to: '/workflow' },
    { id: 'library', labelKey: 'library', icon: BookOpen, to: '/library' },
    { id: 'settings', labelKey: 'settings', icon: Settings, to: '/settings' },
  ];
  const platformItems: NavItem[] = [
    { id: 'flaky', labelKey: 'flaky', icon: Flame, to: '/flaky' },
    { id: 'quality', labelKey: 'quality', icon: ShieldCheck, to: '/quality' },
    { id: 'security', labelKey: 'security', icon: Shield, to: '/security' },
    { id: 'workers', labelKey: 'workers', icon: Server, to: '/workers' },
  ];

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return null;
    const filter = (items: NavItem[]) =>
      items.filter((item) => t(item.labelKey).toLowerCase().includes(needle));
    return { primary: filter(navItems), platform: filter(platformItems) };
  }, [query, t, navItems, platformItems]);

  const renderItem = (item: NavItem) => {
    const Icon = item.icon;
    const label = t(item.labelKey);
    return (
      <NavLink
        key={item.id}
        to={item.to}
        end={item.end}
        title={label}
        className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
      >
        <Icon size={ICON_SIZE} strokeWidth={ICON_STROKE} />
        <span>{label}</span>
      </NavLink>
    );
  };

  return (
    <aside className="app-sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo-icon" aria-hidden="true">
          QA
        </div>
        <span className="sidebar-brand-title">{t('common:appName')}</span>
      </div>

      <div className="sidebar-search">
        <Search size={15} strokeWidth={ICON_STROKE} />
        <input
          type="search"
          value={query}
          placeholder={t('common:search')}
          aria-label={t('common:search')}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key !== 'Enter') return;
            const first = matches?.primary[0] ?? matches?.platform[0];
            if (first) {
              navigate(first.to);
              setQuery('');
            }
          }}
        />
        {!query && (
          <kbd>
            <Command size={11} strokeWidth={ICON_STROKE} />F
          </kbd>
        )}
      </div>

      <div className="sidebar-divider" />

      <nav className="sidebar-nav">
        {matches ? (
          <>
            {matches.primary.map(renderItem)}
            {matches.platform.map(renderItem)}
            {matches.primary.length === 0 && matches.platform.length === 0 && (
              <p className="sidebar-empty">{t('common:noResults')}</p>
            )}
          </>
        ) : (
          <>
            {navItems.map(renderItem)}
            <div className="sidebar-divider" />
            <details key={platformItems.some((item) => pathname.startsWith(item.to)) ? 'platform-active' : 'platform-idle'} className="sidebar-platform" open={platformItems.some((item) => pathname.startsWith(item.to))}>
              <summary className="sidebar-section-label">{t('nav:platform')}</summary>
              {platformItems.map(renderItem)}
            </details>
          </>
        )}
      </nav>

      <div className="sidebar-footer">
        <span className="lang-badge">
          <span>
            {i18n.resolvedLanguage === 'zh-CN'
              ? SUPPORTED_LANGUAGES.find((l) => l.code === 'zh-CN')?.label ?? '中文'
              : 'English'}
          </span>
        </span>
        <button
          type="button"
          className="sidebar-lang-toggle"
          onClick={() => {
            const next = i18n.resolvedLanguage === 'zh-CN' ? 'en' : 'zh-CN';
            void i18n.changeLanguage(next);
            storeLanguage(next);
          }}
        >
          {i18n.resolvedLanguage === 'zh-CN' ? 'EN' : '中'}
        </button>
      </div>
    </aside>
  );
};
