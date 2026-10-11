import { useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, Code2, Workflow as WorkflowIcon } from 'lucide-react';
import { useProjectScope } from '../../app/ProjectScope';
import {
  buildStudioHref,
  buildWorkspaceHref,
  readWorkspaceContext,
} from '../../app/workspaceContext';
import { RuntimeDetail } from '../runtime/RuntimeDetail';
import { TasksPage } from '../../pages/TasksPage';
import './workflow.css';

export function WorkflowPage() {
  const { t } = useTranslation('workflow');
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { projects, selectedProjectId, selectProject } = useProjectScope();
  const context = readWorkspaceContext(searchParams, selectedProjectId);
  const entity = context.taskId
    ? { kind: 'task' as const, id: context.taskId }
    : context.runId
      ? { kind: 'run' as const, id: context.runId }
      : null;

  useEffect(() => {
    if (context.projectId && selectedProjectId !== context.projectId) {
      selectProject(context.projectId);
      return;
    }
    if (!entity || context.projectId) return;
    let active = true;
    const resolveProject = entity.kind === 'task'
      ? apiGetTaskProject(entity.id)
      : apiGetRunProject(entity.id);
    void resolveProject.then((project) => {
      if (active && project && project !== selectedProjectId) selectProject(project);
    }).catch(() => undefined);
    return () => { active = false; };
  }, [context.projectId, entity?.kind, entity?.id, selectedProjectId, selectProject]);

  const openSource = (file: string, line: number, sourceContext?: { nodeId?: string; testCaseId?: string; failureId?: string; taskId?: string; runId?: string }) => {
    navigate(buildStudioHref({
      ...context,
      ...sourceContext,
      projectId: context.projectId ?? selectedProjectId ?? undefined,
      taskId: sourceContext?.runId ? undefined : sourceContext?.taskId ?? context.taskId,
      file,
      lineNumber: line,
      returnTo: context.failureId ? 'workspace' : context.returnTo,
      stage: context.failureId ? 'failure' : context.stage,
    }));
  };

  if (!entity) {
    return <TasksPage projects={projects} selectedProjectId={context.projectId ?? selectedProjectId} />;
  }

  const workspaceContext = {
    ...context,
    projectId: context.projectId ?? selectedProjectId ?? undefined,
    taskId: entity.kind === 'task' ? entity.id : undefined,
    runId: entity.kind === 'run' ? entity.id : context.runId,
    stage: context.failureId ? 'failure' as const : context.runId ? 'result' as const : context.stage,
  };
  const project = projects.find((item) => item.id === workspaceContext.projectId);
  return (
    <div className="workflow-page">
      <header className="workflow-page-heading">
        <div>
          <span className="workspace-eyebrow">{t('eyebrow')} · {project?.name ?? workspaceContext.projectId ?? t('allProjects')}</span>
          <h1><WorkflowIcon size={19} aria-hidden="true" />{t('title')}</h1>
          <p>{t('subtitle')}</p>
        </div>
        <nav aria-label={t('contextActions')}>
          {workspaceContext.projectId && <Link className="btn btn-secondary btn-sm" to={buildWorkspaceHref(workspaceContext)}><ArrowLeft size={14} aria-hidden="true" />{t('backToWorkspace')}</Link>}
          {workspaceContext.projectId && workspaceContext.file && <Link className="btn btn-secondary btn-sm" to={buildStudioHref(workspaceContext)}><Code2 size={14} aria-hidden="true" />{t('openStudio')}</Link>}
          {entity.kind === 'task' && <Link className="btn btn-secondary btn-sm" to={`/workflow${workspaceContext.projectId ? `?projectId=${encodeURIComponent(workspaceContext.projectId)}` : ''}`}>{t('allTasks')}</Link>}
        </nav>
      </header>
      <section className="workflow-canvas-surface">
        <RuntimeDetail
          key={`${entity.kind}:${entity.id}`}
          kind={entity.kind}
          id={entity.id}
          projectId={workspaceContext.projectId}
          onOpenSource={openSource}
          onOpenStudio={() => navigate(buildStudioHref({ ...workspaceContext, taskId: entity.kind === 'task' ? entity.id : undefined, runId: undefined }))}
        />
      </section>
    </div>
  );
}

async function apiGetTaskProject(taskId: string): Promise<string | null> {
  const { api } = await import('../../api/client');
  return (await api.getTask(taskId)).project_id ?? null;
}

async function apiGetRunProject(runId: string): Promise<string | null> {
  const { api } = await import('../../api/client');
  return (await api.getTestRun(runId)).project_id ?? null;
}
