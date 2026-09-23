import React from 'react';
import { NavLink } from 'react-router-dom';
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
  | 'workers';

interface NavItem {
  id: NavTab;
  label: string;
  icon: React.ComponentType<{ size?: number }>;
  to: string;
  end?: boolean;
}

export const Navigation: React.FC = () => {
  const { selectedProjectId } = useProjectScope();
  const projectBase = selectedProjectId ? `/projects/${selectedProjectId}` : null;

  const navItems: NavItem[] = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, to: '/', end: true },
    { id: 'projects', label: 'Projects', icon: FolderGit2, to: '/projects', end: true },
    {
      id: 'requirements',
      label: 'Requirements',
      icon: FileText,
      to: projectBase ? `${projectBase}/requirements` : '/requirements',
    },
    { id: 'test_cases', label: 'Test Cases', icon: CheckSquare, to: '/test-cases' },
    {
      id: 'automation',
      label: 'Automation Studio',
      icon: Code2,
      to: projectBase ? `${projectBase}/studio` : '/projects',
    },
    { id: 'runs', label: 'Runs & Runners', icon: PlayCircle, to: '/runs' },
    { id: 'workers', label: 'Distributed Workers', icon: Server, to: '/workers' },
    { id: 'flaky', label: 'Flaky Intelligence', icon: Flame, to: '/flaky' },
    { id: 'failures', label: 'Failures & Healing', icon: AlertTriangle, to: '/failures' },
    { id: 'quality', label: 'Quality & Release', icon: ShieldCheck, to: '/quality' },
    { id: 'security', label: 'Security & RBAC', icon: Shield, to: '/security' },
  ];

  return (
    <aside className="app-sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo-icon">QA</div>
        <div>
          <div className="sidebar-brand-title">AI QA Platform</div>
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
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <span>Engine: Production QA</span>
        <span>AI Ready</span>
      </div>
    </aside>
  );
};
