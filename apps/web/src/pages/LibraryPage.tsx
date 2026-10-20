import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowRight, Bug, CheckSquare, FileText, FolderGit2, History } from 'lucide-react';
import { api } from '../api/client';
import { useProjectScope } from '../app/ProjectScope';
import type { FailureRecord, Requirement, TestCase, TestRun } from '../types';
import './library.css';

export function LibraryPage() {
  const { t } = useTranslation('library');
  const { projects, selectedProjectId } = useProjectScope();
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [cases, setCases] = useState<TestCase[]>([]);
  const [runs, setRuns] = useState<TestRun[]>([]);
  const [failures, setFailures] = useState<FailureRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [loadAttempt, setLoadAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    setRequirements([]);
    setCases([]);
    setRuns([]);
    setFailures([]);
    void Promise.all([
      api.getRequirements(selectedProjectId ?? undefined),
      api.getTestCases(selectedProjectId ?? undefined),
      api.getTestRuns(selectedProjectId ?? undefined, 8),
      api.getFailures(selectedProjectId ?? undefined, 8),
    ]).then(([nextRequirements, nextCases, nextRuns, nextFailures]) => {
      if (!active) return;
      setRequirements(nextRequirements);
      setCases(nextCases);
      setRuns(nextRuns);
      setFailures(nextFailures);
    }).catch((reason: unknown) => {
      if (active) setError(reason instanceof Error ? reason.message : String(reason));
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [selectedProjectId, loadAttempt]);

  const projectPath = (path: string) => selectedProjectId ? `/projects/${selectedProjectId}${path}` : path;
  const entries = [
    { key: 'projects', label: t('projects'), count: projects.length, href: '/projects', icon: FolderGit2 },
    { key: 'requirements', label: t('requirements'), count: requirements.length, href: projectPath('/requirements'), icon: FileText },
    { key: 'cases', label: t('cases'), count: cases.length, href: projectPath('/test-cases'), icon: CheckSquare },
    { key: 'runs', label: t('runs'), count: runs.length === 8 ? '8+' : runs.length, href: selectedProjectId ? `/runs?projectId=${selectedProjectId}` : '/runs', icon: History },
    { key: 'failures', label: t('failures'), count: failures.length === 8 ? '8+' : failures.length, href: selectedProjectId ? `/failures?projectId=${selectedProjectId}` : '/failures', icon: Bug },
  ];

  return (
    <div className="library-page">
      <header className="library-heading"><span className="workspace-eyebrow">{t('eyebrow')}</span><h1>{t('title')}</h1><p>{t('subtitle')}</p></header>
      {error && <div className="library-error" role="alert"><span>{error}</span><button className="btn btn-secondary btn-sm" type="button" onClick={() => setLoadAttempt((value) => value + 1)}>{t('retry')}</button></div>}
      {loading && <p className="library-loading" role="status">{t('loading')}</p>}
      {!loading && !error && <>
      <section className="library-grid" aria-label={t('collections')}>
        {entries.map(({ key, label, count, href, icon: Icon }) => <Link key={key} to={href} className="library-card">
          <div className="library-card-icon"><Icon size={18} aria-hidden="true" /></div>
          <span>{label}</span><strong>{count}</strong><small>{t(`description.${key}`)}</small><ArrowRight className="library-card-arrow" size={16} aria-hidden="true" />
        </Link>)}
      </section>
      <section className="library-recent-grid">
        <div className="library-list-card"><h2>{t('recentRuns')}</h2>{runs.slice(0, 5).map((run) => <Link key={run.id} to={`/runs/${run.id}`}><span className={`workspace-status-mark is-${run.status.toLowerCase()}`} aria-hidden="true" /><strong>{run.requested_by || run.id.slice(0, 8)}</strong><small>{run.status} · {run.passed}/{run.total || '—'}</small></Link>)}{!runs.length && <p>{t('empty')}</p>}</div>
        <div className="library-list-card"><h2>{t('recentFailures')}</h2>{failures.slice(0, 5).map((failure) => <Link key={failure.id} to={`/failures/${failure.id}`}><span className="workspace-status-mark is-failed" aria-hidden="true" /><strong>{failure.test_name || failure.test_nodeid}</strong><small>{failure.classification}</small></Link>)}{!failures.length && <p>{t('empty')}</p>}</div>
      </section>
      <div className="library-secondary-links"><Link to="/projects">{t('projectManagement')}</Link><Link to={projectPath('/requirements')}>{t('requirementManagement')}</Link><Link to={projectPath('/test-cases')}>{t('caseManagement')}</Link></div>
      </>}
    </div>
  );
}
