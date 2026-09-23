import React from 'react';
import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import i18n from '../i18n';
import {
  LayoutDashboard,
  FolderGit2,
  FileText,
  CheckSquare,
  Code2,
  PlayCircle,
  AlertTriangle,
  Flame,
  ShieldCheck,
  Shield,
  Server,
  Settings,
} from 'lucide-react';
import { useProjectScope } from '../app/ProjectScope';

export type NavTab =
  | 'dashboard'
  | 'projects'
  | 'requirements'
  | 'test_cases'
  | 'automation'
  | 'runs'
  | 'flaky'
  | 'failures'
  | 'quality'
  | 'security'
  | 'workers'
  | 'settings';

interface NavItem {
  id: NavTab;
  labelKey: string;
  icon: React.ComponentType<{ size?: number }>;
  to: string;
  end?: boolean;
}

export const Navigation: React.FC = () => {
  const { t } = useTranslation('nav');
  const { selectedProjectId } = useProjectScope();
  const projectBase = selectedProjectId ? `/projects/${selectedProjectId}` : null;

  const navItems: NavItem[] = [
    { id: 'dashboard', labelKey: 'dashboard', icon: LayoutDashboard, to: '/', end: true },
    { id: 'projects', labelKey: 'projects', icon: FolderGit2, to: '/projects', end: true },
    {
      id: 'requirements',
      labelKey: 'requirements',
      icon: FileText,
      to: projectBase ? `${projectBase}/requirements` : '/requirements',
    },
    { id: 'test_cases', labelKey: 'testCases', icon: CheckSquare, to: '/test-cases' },
    {
      id: 'automation',
      labelKey: 'automation',
      icon: Code2,
      to: projectBase ? `${projectBase}/studio` : '/projects',
    },
    { id: 'runs', labelKey: 'runs', icon: PlayCircle, to: '/runs' },
    { id: 'workers', labelKey: 'workers', icon: Server, to: '/workers' },
    { id: 'flaky', labelKey: 'flaky', icon: Flame, to: '/flaky' },
    { id: 'failures', labelKey: 'failures', icon: AlertTriangle, to: '/failures' },
    { id: 'quality', labelKey: 'quality', icon: ShieldCheck, to: '/quality' },
    { id: 'security', labelKey: 'security', icon: Shield, to: '/security' },
    { id: 'settings', labelKey: 'settings', icon: Settings, to: '/settings' },
  ];

  return (
    <aside className="app-sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo-icon">QA</div>
        <div>
          <div className="sidebar-brand-title">{t('common:appName')}</div>
        </div>
        <span className="sidebar-brand-badge">v0.3</span>
      </div>

      <nav className="sidebar-nav">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.id}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            >
              <Icon size={16} />
              <span>{t(item.labelKey)}</span>
            </NavLink>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <span>Engine: Production QA</span>
        <span>{i18n.resolvedLanguage === 'zh-CN' ? '中文' : 'EN'}</span>
      </div>
    </aside>
  );
};
