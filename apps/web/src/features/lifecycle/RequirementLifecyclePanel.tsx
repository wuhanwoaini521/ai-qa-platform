import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Check, Circle, LoaderCircle, Sparkles, X } from 'lucide-react';
import { api } from '../../api/client';
import type { AITraceEvent, Requirement, TestDesign } from '../../types';
import { useKnowledge } from './useKnowledge';
import { KnowledgeGraph } from './KnowledgeGraph';
import { CoveragePanel } from './CoveragePanel';
import { Journey } from './Journey';
import './lifecycle.css';

function isInvalidStructuredAnalysis(code: string | undefined, message: string | undefined) {
  return code === 'INVALID_STRUCTURED_OUTPUT' || Boolean(message?.includes('Invalid JSON') && message.includes('RequirementAnalysis'));
}

type ProviderFailureMessageKey = 'providerAnalysisFailed' | 'providerOutputLimit' | 'providerEmptyResponse' | 'providerUnavailable';

function providerFailureMessageKey(code: string | undefined, message: string | undefined): ProviderFailureMessageKey | undefined {
  const normalizedCode = code?.toLowerCase();
  if (normalizedCode === 'output_limit') return 'providerOutputLimit';
  if (normalizedCode === 'empty_stream' || normalizedCode === 'empty_response') return 'providerEmptyResponse';
  if (['provider_unavailable', 'timeout', 'network_error', 'authentication_failed', 'permission_denied', 'rate_limited', 'upstream_error'].includes(normalizedCode ?? '')) return 'providerUnavailable';
  if (message && /output length limit|exhausted the .* output limit|输出长度上限/i.test(message)) return 'providerOutputLimit';
  if (message && /empty (stream|response)|没有返回可用文本/i.test(message)) return 'providerEmptyResponse';
  if (message && /AI completion timed out|OpenAI completion failed after \d+ retries|AI connection attempts failed/i.test(message)) return 'providerUnavailable';
  return undefined;
}

export function RequirementLifecyclePanel({requirement, onChanged, onCaseCreated, onStartAnalysis, analysisRunning = false, showAnalyzeAction = true, showJourney = true}: {requirement: Requirement; onChanged: (item: Requirement) => void; onCaseCreated?: (testCaseId: string, testDesignId?: string) => void; onStartAnalysis?: () => Promise<void>; analysisRunning?: boolean; showAnalyzeAction?: boolean; showJourney?: boolean}) {
  const {t} = useTranslation('lifecycle');
  const [query, setQuery] = useSearchParams();
  const tab = query.get('tab')??'overview';
  const knowledge = useKnowledge(requirement.project_id, requirement.id);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [events, setEvents] = useState<AITraceEvent[]>([]);
  const [designs, setDesigns] = useState<TestDesign[]>([]);
  const [activeHistory, setActiveHistory] = useState('');
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const runtimeAnalysisObserved = useRef(false);
  const analysisRecordBeforeRuntime = useRef<string | null>(null);
  useEffect(() => {
    let disposed = false;
    generation.current++; setEvents([]);setBusy(false);setError('');setDesigns([]);setActiveHistory('');
    api.getTestDesigns(requirement.id).then(items=>{if(!disposed)setDesigns(items);}).catch(reason=>{if(!disposed)setError(String(reason));});
    return () => {disposed=true;generation.current++;controller.current?.abort();};
  }, [requirement.id]);
  const analyze = async () => {
    const token=generation.current; const aborter = new AbortController();controller.current=aborter;
    setBusy(true);setError('');setEvents([]);setActiveHistory('');setQuery({...Object.fromEntries(query),tab:'analysis'});
    if(onStartAnalysis){
      try { await onStartAnalysis(); }
      catch(reason){ if(token===generation.current)setError(String(reason)); }
      finally { if(token===generation.current)setBusy(false); }
      return;
    }
    try {await api.streamRequirementLifecycle(requirement.id,event=>{if(token===generation.current)setEvents(items=>[...items,event].slice(-60));},aborter.signal);}
    catch(reason){if(token===generation.current&&!aborter.signal.aborted)setError(String(reason));}
    finally {if(token===generation.current){setBusy(false);try{onChanged(await api.getRequirement(requirement.id));knowledge.reload();}catch(reason){setError(String(reason));}}}
  };
  const adopt = async () => {
    setBusy(true);setError('');const token=generation.current;
    try {const items=await api.adoptLifecycleDesigns(requirement.id);if(token===generation.current){setDesigns(items);knowledge.reload();}}
    catch(reason){if(token===generation.current)setError(String(reason));}finally{if(token===generation.current)setBusy(false);}
  };
  const doc = requirement.qa_model;
  const history = doc?.history??[];
  const latestRecord = history.at(-1);
  const record = history.find(item=>item.id===activeHistory)??history.at(-1);
  useEffect(() => {
    if (analysisRunning) {
      if (!runtimeAnalysisObserved.current) {
        analysisRecordBeforeRuntime.current = latestRecord?.status === 'RUNNING'
          ? history.at(-2)?.id ?? null
          : latestRecord?.id ?? null;
      }
      runtimeAnalysisObserved.current = true;
      return;
    }
    if (!runtimeAnalysisObserved.current) return;
    runtimeAnalysisObserved.current = false;
    if (latestRecord?.status === 'SUCCESS' && latestRecord.id !== analysisRecordBeforeRuntime.current) {
      setQuery({...Object.fromEntries(query), tab: 'design'});
    }
  }, [analysisRunning, history, latestRecord?.id, latestRecord?.status, query, setQuery]);
  const displayedAnalysis = activeHistory ? record?.analysis_snapshot : doc?.analysis;
  const showingPreviousAnalysis = !activeHistory && Boolean(latestRecord && !['SUCCESS', 'REFERENCE'].includes(latestRecord.status) && doc?.analysis);
  const stages = busy && events.length ? Object.values(Object.fromEntries(events.filter(event=>event.type==='workflow.step').map(event=>[event.stage,{id:event.stage,title:event.title,status:(event.status??'pending').toLowerCase()==='completed'?'passed':(event.status??'pending').toLowerCase(),summary:event.message,source:String(event.metadata?.source??''),duration_ms:event.duration_ms??0}]))) : record?.stages??[];
  const recordProviderFailure = providerFailureMessageKey(record?.error_code, record?.error);
  return <section className="lc-page">
    <nav className="lc-breadcrumb"><Link to={`/projects/${requirement.project_id}`}>{t('projectWorkspace')}</Link><span>/</span><span>{doc?.display_id||requirement.title}</span></nav>
    <div className="lc-header"><div><span className="lc-eyebrow">{doc?.display_id||'Requirement'} · {requirement.status}</span><h2>{requirement.title}</h2></div>{showAnalyzeAction && <button className="btn btn-primary" disabled={busy||analysisRunning} onClick={()=>void analyze()}><Sparkles size={15}/>{busy||analysisRunning?t('analyzing'):t('analyze')}</button>}</div>
    {showJourney&&knowledge.graph&&<Journey graph={knowledge.graph} active="requirement" analysisDone={history.at(-1)?.status==='SUCCESS'}/>}
    <nav className="lc-tabs">{['overview','analysis','mind','scenario','knowledge','coverage','design'].map(key=><button key={key} className={tab===key?'selected':''} onClick={()=>setQuery({...Object.fromEntries(query),tab:key})}>{t(key)}</button>)}</nav>
    {(error||knowledge.error)&&<p role="alert" className="lc-notice lc-error">{error||knowledge.error}</p>}
    {requirement.analysis_stale&&<p className="lc-notice">{t('staleAnalysis')}</p>}
    {tab==='overview'&&<><section className="lc-card"><p>{requirement.description}</p><h3>{t('acceptanceCriteria')}</h3>{doc?.criteria.length?doc.criteria.map(item=><div className="lc-gap" key={item.id}><strong>{item.id}</strong><span>{item.description}</span>{item.negative_required&&<small>{t('negativeRequired')}</small>}</div>):<pre>{requirement.acceptance_criteria}</pre>}</section><div className="lc-two-col"><section className="lc-card"><h3>{t('rules')}</h3>{doc?.rules.map(item=><p key={item.id}><strong>{item.id}</strong> · {item.description}<small className="lc-muted"> ({item.criterion_ids.join(', ')})</small></p>)}</section><section className="lc-card"><h3>{t('constraints')}</h3>{[...(doc?.constraints??[]),...(doc?.dependencies??[])].map((item,index)=><p key={index}>{item}</p>)}</section></div></>}
    {tab==='analysis'&&<><section className="lc-card"><div className="lc-toolbar"><h3>{busy?t('analyzing'):t('analysisHistory')}</h3><select aria-label={t('analysisHistory')} value={activeHistory||record?.id||''} onChange={e=>setActiveHistory(e.target.value)}>{[...history].reverse().map(item=><option key={item.id} value={item.id}>{item.status} · {item.provider||'—'} · {new Date(item.started_at).toLocaleString()}</option>)}</select>{busy&&<button className="btn btn-secondary btn-sm" onClick={()=>controller.current?.abort()}>{t('cancel')}</button>}</div>
      {record?.status==='REFERENCE'&&<p className="lc-notice">{t('referenceNotice')}</p>}{record?.error&&<div className="lc-notice lc-error" role="alert"><p>{isInvalidStructuredAnalysis(record.error_code,record.error)?t('invalidStructuredOutput'):recordProviderFailure?t(recordProviderFailure):record.error}</p>{(isInvalidStructuredAnalysis(record.error_code,record.error)||recordProviderFailure)&&<details><summary>{t('technicalDetails')}</summary><pre>{record.error}</pre></details>}</div>}
      {record&&<p className="lc-caption">{record.provider||'—'} · {record.model||'—'} · {record.prompt_version||'—'} · {record.id}</p>}
      {stages.map(stage=>{const providerFailure=providerFailureMessageKey(stage.id==='semantic'&&stage.status==='failed'?record?.error_code:undefined,stage.summary);return <div key={stage.id} className={`lc-stage ${stage.status}`}><span className="lc-stage-icon">{stage.status==='passed'?<Check size={18}/>:stage.status==='failed'?<X size={18}/>:stage.status==='running'?<LoaderCircle size={18}/>:<Circle size={18}/>}</span><div><strong>{stage.title}</strong><span>{isInvalidStructuredAnalysis(stage.id === 'semantic' ? record?.error_code : undefined,stage.summary)?t('invalidStructuredOutput'):providerFailure?t(providerFailure):stage.summary}</span></div><small>{stage.source} · {Math.round(stage.duration_ms)} ms</small></div>;})}
      {record?.decisions.map(item=><div className="lc-notice" key={item.name}><strong>Jev · {item.name}</strong><p>{item.choice??t('abstained')} · {item.provider} · {item.model}</p><small>{item.reason||t('decisionEvidence')} {item.fallback_used&&t('localFallback')}</small></div>)}
      {!history.length&&!busy&&<p className="lc-empty">{t('noAnalysis')}</p>}
    </section>{showingPreviousAnalysis&&<p className="lc-notice">{t('previousAnalysisNotice')}</p>}{displayedAnalysis&&<><section className="lc-card"><h3>{t('semanticSummary')}</h3><p>{displayedAnalysis.summary}</p><div className="lc-chip-list">{displayedAnalysis.actors.concat(displayedAnalysis.entities).map((item,index)=><span className="lc-chip" key={index}>{item}</span>)}</div><details><summary>{t('assumptions')}</summary>{displayedAnalysis.assumptions.concat(displayedAnalysis.dependencies).map((item,index)=><p key={index}>{item}</p>)}</details>{displayedAnalysis.ambiguities.map(item=><p className="lc-notice" key={item.id}>{item.question} · {item.impact}</p>)}</section><div className="lc-stack">{displayedAnalysis.risks.map(item=><section className="lc-card" key={item.id}><div className="lc-toolbar"><strong>{item.id} · {item.title}</strong><span className="badge badge-draft">{item.severity}</span></div><p>{item.impact}</p><p className="lc-caption">{item.criterion_ids.join(' · ')} · {item.rationale}</p></section>)}</div></>}</>}
    {['mind','scenario','knowledge'].includes(tab)&&knowledge.graph&&<KnowledgeGraph graph={knowledge.graph} mode={tab} initialNode={query.get('node')??undefined}/>}
    {tab==='coverage'&&knowledge.graph&&<CoveragePanel graph={knowledge.graph}/>}
    {tab==='design'&&<><div className="lc-toolbar"><p className="lc-muted">{t('designIntent')}</p><button className="btn btn-primary" disabled={busy||!doc?.analysis} onClick={()=>void adopt()}>{t('adoptDesigns')}</button></div><div className="lc-stack">{(doc?.analysis?.scenarios??[]).map(scenario=>{const design=designs.find(d=>d.scenario_model?.id===scenario.id);return <section className="lc-card" key={scenario.id}><div className="lc-toolbar"><strong>{scenario.id} · {scenario.title}</strong><span className="badge badge-draft">{scenario.priority} · {scenario.technique} · {scenario.path_type}</span></div><p>{scenario.intent}</p><div className="lc-chip-list">{Object.values(scenario.coverage).flat().map(id=><span className="lc-chip" key={id}>{id}</span>)}</div><p className="lc-caption">{scenario.rationale}</p><div className="lc-flow">{scenario.actions.map((action,index)=><div className="lc-flow-step" key={index}><i>{index+1}</i><span>{action}</span></div>)}</div><p>{scenario.expected_outcomes.join('；')}</p>{design&&<button className="btn btn-secondary" disabled={busy} onClick={async()=>{setBusy(true);setError('');try{const item=await api.adoptLifecycleCase(design.id);if(onCaseCreated)onCaseCreated(item.id,item.test_design_id??design.id);else setQuery({...Object.fromEntries(query),tab:'design',caseId:item.id},{replace:true});knowledge.reload();}catch(reason){setError(String(reason));}finally{setBusy(false);}}}>{t('createCase')}</button>}{knowledge.graph?.nodes.filter(n=>n.kind==='case'&&n.metadata.test_model&&(n.metadata.test_model as {scenario_id?:string}).scenario_id===scenario.id).map(node=><Link className="btn btn-secondary" key={node.id} style={{marginLeft:8}} to={node.href}>{t('openCase')} · {node.label}</Link>)}</section>;})}</div></>}
  </section>;
}
