import React from 'react';
import { useTranslation } from 'react-i18next';
import { FolderGit2, Search } from 'lucide-react';
import { Project } from '../../../types';
import { buildProjectDisplayNames } from '../../../app/projectSelectionModel';

interface ProjectSelectorProps {
  projects: Project[];
  currentProjectId: string;
  onSelectProject: (id: string) => void;
  onQuickOpen: () => void;
}

/** Project switcher card: the studio's context, with quick open beside it. */
export const ProjectSelector: React.FC<ProjectSelectorProps> = ({
  projects,
  currentProjectId,
  onSelectProject,
  onQuickOpen,
}) => {
  const { t } = useTranslation('studioShell');
  const projectDisplayNames = buildProjectDisplayNames(projects);
  return (
    <div className="studio-project-select">
      <FolderGit2 size={15} color="var(--ui-primary-strong)" />
      <select aria-label={t('projectSelector.selectProject')} value={currentProjectId} onChange={(e) => onSelectProject(e.target.value)}>
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {projectDisplayNames.get(p.id) ?? p.name}
          </option>
        ))}
      </select>
      <button className="icon-btn" title={t('projectSelector.quickOpen')} onClick={onQuickOpen}>
        <Search size={14} />
      </button>
    </div>
  );
};
