import React from 'react';
import { Download, Plus } from 'lucide-react';
import { Project } from '../../../types';

interface RequirementToolbarProps {
  projects: Project[];
  onOpenJira: () => void;
  onNewRequirement: () => void;
}

export const RequirementToolbar: React.FC<RequirementToolbarProps> = ({
  projects,
  onOpenJira,
  onNewRequirement,
}) => {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
      <div>
        <h2 style={{ fontSize: '18px', fontWeight: 700 }}>Requirement & AI Test Design</h2>
        <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
          AI-assisted requirement testability analysis, risk extraction, and dimensional test design generation.
        </p>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <button
          className="btn btn-secondary"
          disabled={projects.length === 0}
          onClick={onOpenJira}
          title="Import user stories from Atlassian Jira"
        >
          <Download size={15} /> Import from Jira
        </button>
        <button
          className="btn btn-primary"
          disabled={projects.length === 0}
          onClick={onNewRequirement}
        >
          <Plus size={16} /> New Requirement
        </button>
      </div>
    </div>
  );
};
