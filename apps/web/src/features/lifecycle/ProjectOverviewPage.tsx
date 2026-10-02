import { useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowRight, RotateCcw } from 'lucide-react';
import { api } from '../../api/client';
import type { Project, Requirement } from '../../types';
import { useProjectScope, useRouteProjectScope } from '../../app/ProjectScope';
import { useKnowledge } from './useKnowledge';
import { Journey } from './Journey';
import { CoveragePanel } from './CoveragePanel';
import { KnowledgeGraph } from './KnowledgeGraph';
import './lifecycle.css';

export function ProjectOverviewPage() {
  const {projectId = ''} = useParams();
  const {t} = useTranslation('lifecycle');
  const [query, setQuery] = useSearchParams();
  const tab = query.get('tab') ?? 'overview';
  useRouteProjectScope(projectId);
  const scope = useProjectScope();
  const knowledge = useKnowledge(projectId);
  const [project, setProject] = useState<Project | null>(null);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [error, setError] = useState('');
  const [resetting, setResetting] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  useEffect(() => {
    let disposed = false;
    Promise.all([api.getProject(projectId),api.getRequirements(projectId)]).then(([p,r]) => {
      if (!disposed) {setProject(p);setRequirements(r);}
    }).catch(reason => {if(!disposed)setError(String(reason));});
    return () => {disposed=true;};
  }, [projectId, knowledge.graph]);
  const reset = async () => {
    setResetting(true); setError('');
    try {await api.resetGoldenDemo(projectId);knowledge.reload();await scope.refresh();setConfirmReset(false);}
    catch(reason){setError(String(reason));}finally{setResetting(false);}
  };
  const root = `/projects/${projectId}`;
  return <main className="lc-page"><nav className="lc-breadcrumb"><Link to="/projects">{t('projects')}</Link><span>/</span><span>{project?.name??projectId}</span></nav>
    <div className="lc-header"><div><span className="lc-eyebrow">{t('projectWorkspace')}</span><h2>{project?.name??t('loading')}</h2><p className="lc-muted">{project?.description}</p></div><div className="lc-toolbar"><button className="btn btn-secondary" onClick={knowledge.reload}>{t('refresh')}</button>{project?.demo_kind==='golden_shop_v1'&&<button className="btn btn-secondary" onClick={()=>setConfirmReset(true)}><RotateCcw size={14}/>{t('resetDemo')}</button>}</div></div>
    {(error||knowledge.error)&&<p role="alert" className="lc-notice lc-error">{error||knowledge.error}</p>}
    {confirmReset&&<div className="lc-notice"><p>{t('resetWarning')}</p><div className="lc-toolbar"><button className="btn btn-primary" disabled={resetting} onClick={()=>void reset()}>{resetting?t('loading'):t('confirmReset')}</button><button className="btn btn-secondary" onClick={()=>setConfirmReset(false)}>{t('cancel')}</button></div></div>}
    {knowledge.graph&&<Journey graph={knowledge.graph} analysisDone={requirements.some(req=>req.qa_model?.history.at(-1)?.status==='SUCCESS')} />}
    <nav className="lc-tabs"><button className={tab==='overview'?'selected':''} onClick={()=>setQuery({tab:'overview'})}>{t('overview')}</button><button className={tab==='knowledge'?'selected':''} onClick={()=>setQuery({tab:'knowledge'})}>{t('knowledge')}</button><button className={tab==='coverage'?'selected':''} onClick={()=>setQuery({tab:'coverage'})}>{t('coverage')}</button><Link to={`${root}/requirements`}>{t('requirements')}</Link><Link to={`${root}/test-cases`}>{t('cases')}</Link><Link to={`${root}/studio`}>Studio</Link><Link to="/runs">{t('runs')}</Link></nav>
    {knowledge.loading&&<p className="lc-empty" role="status">{t('loading')}</p>}
    {knowledge.graph&&tab==='overview'&&<><div className="lc-metric-grid">{['requirement','design','case','automated','executed','passed'].map(kind=><div key={kind} className="lc-metric"><span>{t(`count.${kind}`)}</span><strong>{knowledge.graph!.counts[kind]??0}</strong><small>{t('actualRecords')}</small></div>)}</div><div className="lc-two-col"><section className="lc-card"><h3>{t('startFromRequirement')}</h3>{requirements.map(req=><Link key={req.id} className="lc-gap" to={`${root}/requirements/${req.id}`}><strong>{req.qa_model?.display_id||req.id.slice(-6)}</strong><span>{req.title}</span><ArrowRight size={16}/></Link>)}{!requirements.length&&<p className="lc-muted">{t('noRequirement')}</p>}</section><section className="lc-card"><h3>{t('attention')}</h3><p>{t('coverageGapCount',{count:knowledge.graph.gaps.length})}</p><p className="lc-muted">{t('executionMeaning')}</p><Link className="btn btn-secondary" to={`${root}?tab=coverage`}>{t('inspectCoverage')}</Link>{project?.demo_kind&&<a className="btn btn-secondary" style={{marginLeft:8}} href="/api/demo-shop/index.html" target="_blank" rel="noreferrer">{t('openShop')}</a>}</section></div></>}
    {knowledge.graph&&tab==='knowledge'&&<KnowledgeGraph graph={knowledge.graph} initialNode={query.get('node')??undefined}/>}
    {knowledge.graph&&tab==='coverage'&&<CoveragePanel graph={knowledge.graph}/>}
  </main>;
}
