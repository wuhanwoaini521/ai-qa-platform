import React from 'react';
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
} from 'lucide-react';

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
  | 'security';

interface NavigationProps {
  currentTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
}

export const Navigation: React.FC<NavigationProps> = ({ currentTab, onSelectTab }) => {
  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'projects', label: 'Projects', icon: FolderGit2 },
    { id: 'requirements', label: 'Requirements', icon: FileText },
    { id: 'test_cases', label: 'Test Cases', icon: CheckSquare },
    { id: 'automation', label: 'Automation Studio', icon: Code2 },
    { id: 'runs', label: 'Runs & Runners', icon: PlayCircle },
    { id: 'flaky', label: 'Flaky Intelligence', icon: Flame },
    { id: 'failures', label: 'Failures & Healing', icon: AlertTriangle },
    { id: 'quality', label: 'Quality & Release', icon: ShieldCheck },
    { id: 'security', label: 'Security & RBAC', icon: Shield },
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
          const isActive = currentTab === item.id;
          return (
            <div
              key={item.id}
              className={`nav-item ${isActive ? 'active' : ''}`}
              onClick={() => onSelectTab(item.id as NavTab)}
            >
              <Icon size={16} />
              <span>{item.label}</span>
            </div>
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
