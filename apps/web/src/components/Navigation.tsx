import React, { useEffect, useMemo, useRef, useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  LayoutDashboard,
  PanelsTopLeft,
  GitBranch,
  FolderGit2,
  Flame,
  ShieldCheck,
  Shield,
  Server,
  Settings,
  Search,
  ClipboardList,
  Bug,
  Radio,
  PanelLeftClose,
  PanelLeftOpen,
  MoreHorizontal,
  ChevronDown,
} from 'lucide-react';
import i18n, { storeLanguage, SUPPORTED_LANGUAGES } from '../i18n';
import { useProjectScope } from '../app/ProjectScope';
import { buildWorkspaceHref } from '../app/workspaceContext';
import { withProjectId } from '../app/projectPaths';
import { Tooltip } from './Tooltip';

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
  | 'discovery'
  | 'workflow'
  | 'library';

interface NavItem {
  id: NavTab;
  labelKey: string;
  icon: React.ComponentType<{
    size?: number;
    strokeWidth?: number;
    'aria-hidden'?: boolean;
  }>;
  to: string;
  end?: boolean;
  mobileLabelKey?: string;
}

interface QuickDestination {
  id: string;
  label: string;
  icon: NavItem['icon'];
  to: string;
  keywords: string[];
}

const ICON_SIZE = 18;
const ICON_STROKE = 1.6;
const SIDEBAR_COLLAPSED_KEY = 'ai-qa.sidebar-collapsed';

/** Project context and searchable destinations in an expandable navigation rail. */
export const Navigation: React.FC = () => {
  const { t } = useTranslation('nav');
  const { t: workspaceT } = useTranslation('workspace');
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { projects, selectedProjectId, selectProject } = useProjectScope();
  const [query, setQuery] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return typeof window !== 'undefined' && window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true';
    } catch {
      return false;
    }
  });
  const searchInputRef = useRef<HTMLInputElement>(null);
  const paletteInputRef = useRef<HTMLInputElement>(null);
  const paletteRef = useRef<HTMLElement>(null);

  useEffect(() => {
    try {
      window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(collapsed));
    } catch {
      // Keep the sidebar usable when storage is unavailable.
    }
  }, [collapsed]);

  useEffect(() => {
    const focusNavigationSearch = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== 'k') return;
      event.preventDefault();
      setSearchOpen(true);
    };
    window.addEventListener('keydown', focusNavigationSearch);
    return () => window.removeEventListener('keydown', focusNavigationSearch);
  }, []);

  useEffect(() => {
    if (!searchOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    paletteInputRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setSearchOpen(false);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      previous?.focus();
    };
  }, [searchOpen]);

  const navigateTo = (to: string) => {
    navigate(to);
    setQuery('');
    setSearchOpen(false);
  };

  const workspaceBase = selectedProjectId ? `/workspace/${selectedProjectId}` : '/workspace';
  const workspaceRoute = pathname === '/workspace' || pathname.startsWith('/workspace/');
  const projectScopedRoute = (workspaceRoute && pathname !== '/workspace') || pathname.startsWith('/projects/');
  const handleProjectChange = (projectId: string) => {
    const nextProjectId = projectId || null;
    // Navigate before updating selection so the outgoing route cannot restore stale scope.
    navigate(withProjectId(pathname, nextProjectId));
    selectProject(nextProjectId);
  };

  const navItems: NavItem[] = [
    { id: 'dashboard', labelKey: 'dashboard', mobileLabelKey: 'dashboardMobile', icon: LayoutDashboard, to: '/', end: true },
    { id: 'workspace', labelKey: 'workspace', mobileLabelKey: 'workspaceMobile', icon: PanelsTopLeft, to: workspaceBase },
    { id: 'projects', labelKey: 'projects', mobileLabelKey: 'projectsMobile', icon: FolderGit2, to: '/projects' },
    { id: 'runs', labelKey: 'runs', mobileLabelKey: 'runsMobile', icon: GitBranch, to: '/runs' },
    { id: 'quality', labelKey: 'quality', mobileLabelKey: 'qualityMobile', icon: ShieldCheck, to: '/quality' },
  ];
  const settingsItem: NavItem = { id: 'settings', labelKey: 'settings', icon: Settings, to: '/settings' };
  const platformItems: NavItem[] = [
    { id: 'flaky', labelKey: 'flaky', icon: Flame, to: '/flaky' },
    { id: 'security', labelKey: 'security', icon: Shield, to: '/security' },
    { id: 'workers', labelKey: 'workers', icon: Server, to: '/workers' },
  ];

  const quickDestinations: QuickDestination[] = [
    {
      id: 'requirement',
      label: workspaceT('quick.requirement'),
      icon: ClipboardList,
      to: buildWorkspaceHref({ projectId: selectedProjectId ?? undefined, stage: 'requirement', view: 'requirement' }),
      keywords: ['requirement', 'requirements', '需求'],
    },
    {
      id: 'cases',
      label: workspaceT('quick.cases'),
      icon: ClipboardList,
      to: buildWorkspaceHref({ projectId: selectedProjectId ?? undefined, stage: 'cases', view: 'cases' }),
      keywords: ['case', 'cases', 'test', 'tests', '用例', '测试'],
    },
    {
      id: 'failures',
      label: workspaceT('quick.failures'),
      icon: Bug,
      to: buildWorkspaceHref({ projectId: selectedProjectId ?? undefined, stage: 'failure', view: 'results' }),
      keywords: ['failure', 'failures', 'failed', '失败', '故障'],
    },
    {
      id: 'recorder',
      label: workspaceT('quick.recorder'),
      icon: Radio,
      to: buildWorkspaceHref({ projectId: selectedProjectId ?? undefined, stage: 'automation', view: 'browser' }),
      keywords: ['recorder', 'recording', '录制', '录制器'],
    },
  ];

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return null;
    const filter = (items: NavItem[]) =>
      items.filter((item) => t(item.labelKey).toLowerCase().includes(needle));
    const workspace = quickDestinations.filter((item) =>
      [item.label, ...item.keywords].some((value) => value.toLowerCase().includes(needle)),
    );
    return { primary: filter([...navItems, settingsItem]), platform: filter(platformItems), workspace };
  }, [query, t, navItems, settingsItem, platformItems, quickDestinations]);

  const renderItem = (item: NavItem) => {
    const Icon = item.icon;
    const label = t(item.labelKey);
    const mobileLabel = t(item.mobileLabelKey ?? item.labelKey);
    return (
      <Tooltip key={item.id} label={label} enabled={collapsed}>
        <NavLink
          to={item.to}
          end={item.end}
          aria-label={label}
          onClick={() => { setQuery(''); setSearchOpen(false); }}
          className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
        >
          <Icon size={ICON_SIZE} strokeWidth={ICON_STROKE} aria-hidden />
          <span className="nav-item-label">{label}</span>
          <span className="nav-item-mobile-label" aria-hidden="true">{mobileLabel}</span>
        </NavLink>
      </Tooltip>
    );
  };

  const renderQuickDestination = (item: QuickDestination) => {
    const Icon = item.icon;
    return (
      <Tooltip key={item.id} label={item.label} enabled={collapsed}>
        <NavLink to={item.to} aria-label={item.label} onClick={() => { setQuery(''); setSearchOpen(false); }} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <Icon size={ICON_SIZE} strokeWidth={ICON_STROKE} aria-hidden />
          <span>{item.label}</span>
        </NavLink>
      </Tooltip>
    );
  };

  return (
    <aside className={`app-sidebar${collapsed ? ' is-collapsed' : ''}`}>
      <div className="sidebar-header">
        <div className="sidebar-logo-icon" title={t('common:appName')} aria-hidden="true">
          QA
        </div>
        {projects.length > 0 && (
          <div className="sidebar-project-context" title={projects.find((project) => project.id === selectedProjectId)?.name ?? t('common:allProjects')}>
            <FolderGit2 className="sidebar-project-icon" size={17} strokeWidth={ICON_STROKE} aria-hidden="true" />
            <select
              className="sidebar-project-select"
              value={selectedProjectId || ''}
              aria-label={t('common:project')}
              onChange={(event) => handleProjectChange(event.target.value)}
            >
              {!projectScopedRoute && <option value="">{t('common:allProjects')}</option>}
              {projects.map((project) => (
                <option key={project.id} value={project.id}>{project.name}</option>
              ))}
            </select>
          </div>
        )}
        <button
          type="button"
          className="sidebar-collapse-toggle"
          aria-label={t(collapsed ? 'expandSidebar' : 'collapseSidebar')}
          aria-expanded={!collapsed}
          aria-controls="primary-sidebar-navigation"
          title={t(collapsed ? 'expandSidebar' : 'collapseSidebar')}
          onClick={() => setCollapsed((value) => !value)}
        >
          {collapsed ? <PanelLeftOpen size={17} strokeWidth={ICON_STROKE} aria-hidden="true" /> : <PanelLeftClose size={17} strokeWidth={ICON_STROKE} aria-hidden="true" />}
        </button>
      </div>

      <button className="sidebar-mobile-search" type="button" aria-label={t('common:search')} title={t('common:search')} onClick={() => setSearchOpen(true)}>
        <Search size={17} strokeWidth={ICON_STROKE} aria-hidden="true" />
      </button>

      <div className="sidebar-search">
        <Search size={15} strokeWidth={ICON_STROKE} />
        <input
          ref={searchInputRef}
          type="search"
          value={query}
          placeholder={t('common:search')}
          aria-label={t('common:search')}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key !== 'Enter') return;
            const first = matches?.primary[0] ?? matches?.platform[0];
            if (first) {
              navigateTo(first.to);
              return;
            }
            const quickDestination = matches?.workspace[0];
            if (quickDestination) {
              navigateTo(quickDestination.to);
            }
          }}
        />
        {!query && <kbd>{/Mac|iPhone|iPad/.test(navigator.userAgent) ? '⌘ K' : 'Ctrl K'}</kbd>}
      </div>

      <div className="sidebar-divider" />

      <nav className="sidebar-nav" id="primary-sidebar-navigation" aria-label={t('primaryNavigation')}>
        {matches ? (
          <>
            {matches.primary.map(renderItem)}
            {matches.platform.map(renderItem)}
            {matches.workspace.map(renderQuickDestination)}
            {matches.primary.length === 0 && matches.platform.length === 0 && matches.workspace.length === 0 && (
              <p className="sidebar-empty">{t('common:noResults')}</p>
            )}
          </>
        ) : (
          <>
            {navItems.map(renderItem)}
            <div className="sidebar-divider" />
            <details key={platformItems.some((item) => pathname.startsWith(item.to)) ? 'platform-active' : 'platform-idle'} className="sidebar-platform" open={platformItems.some((item) => pathname.startsWith(item.to))}>
              <summary className="sidebar-section-label" title={t('nav:platform')}>
                <MoreHorizontal size={ICON_SIZE} strokeWidth={ICON_STROKE} aria-hidden="true" />
                <span>{t('nav:platform')}</span>
                <ChevronDown className="sidebar-section-chevron" size={14} strokeWidth={ICON_STROKE} aria-hidden="true" />
              </summary>
              {platformItems.map(renderItem)}
            </details>
          </>
        )}
      </nav>

      <div className="sidebar-pinned">
        {!matches && renderItem(settingsItem)}
        <div className="sidebar-footer">
          <span className="lang-badge">
            <span>
              {i18n.resolvedLanguage === 'zh-CN'
                ? SUPPORTED_LANGUAGES.find((language) => language.code === 'zh-CN')?.label ?? '中文'
                : 'English'}
            </span>
          </span>
          <button
            type="button"
            className="sidebar-lang-toggle"
            aria-label={t('common:language')}
            title={t('common:language')}
            onClick={() => {
              const next = i18n.resolvedLanguage === 'zh-CN' ? 'en' : 'zh-CN';
              void i18n.changeLanguage(next);
              storeLanguage(next);
            }}
          >
            {i18n.resolvedLanguage === 'zh-CN' ? 'EN' : '中'}
          </button>
        </div>
      </div>

      {searchOpen && <div className="navigation-palette-backdrop" onMouseDown={(event) => {
        if (event.target === event.currentTarget) setSearchOpen(false);
      }}>
        <section
          ref={paletteRef}
          className="navigation-palette"
          role="dialog"
          aria-modal="true"
          aria-label={t('common:search')}
          onKeyDown={(event) => {
            if (event.key !== 'Tab') return;
            const items = paletteRef.current?.querySelectorAll<HTMLElement>('input, a[href], button:not(:disabled)');
            if (!items?.length) return;
            const first = items[0];
            const last = items[items.length - 1];
            if (event.shiftKey && document.activeElement === first) {
              event.preventDefault();
              last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
              event.preventDefault();
              first.focus();
            }
          }}
        >
          <div className="navigation-palette-input">
            <Search size={17} aria-hidden="true" />
            <input
              ref={paletteInputRef}
              type="search"
              value={query}
              aria-label={t('common:search')}
              placeholder={workspaceT('quick.searchPlaceholder')}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key !== 'Enter') return;
                const first = matches?.primary[0] ?? matches?.platform[0];
                const destination = first?.to ?? matches?.workspace[0]?.to ?? quickDestinations[0]?.to;
                if (destination) navigateTo(destination);
              }}
            />
            <kbd>Esc</kbd>
          </div>
          <nav className="navigation-palette-results" aria-label={workspaceT('quick.destinations')}>
            {matches ? <>
              {matches.primary.map(renderItem)}
              {matches.platform.map(renderItem)}
              {matches.workspace.map(renderQuickDestination)}
              {matches.primary.length === 0 && matches.platform.length === 0 && matches.workspace.length === 0 && (
                <p className="sidebar-empty">{t('common:noResults')}</p>
              )}
            </> : quickDestinations.map(renderQuickDestination)}
          </nav>
        </section>
      </div>}
    </aside>
  );
};
