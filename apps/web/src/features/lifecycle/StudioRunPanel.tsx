import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { api } from '../../api/client';
import { LiveBrowserPanel } from '../runs/LiveBrowserPanel';
import { useLiveRun } from '../runs/useLiveRun';

export function StudioRunPanel({runId,projectId,onStep}: {runId:string|null;projectId:string;onStep:(path:string,line:number)=>void}) {
  const {t}=useTranslation('lifecycle'); const live=useLiveRun(runId);const [tab,setTab]=useState('live');const [artifactError,setArtifactError]=useState('');
  const active=live.run&&['RUNNING','QUEUED'].includes(live.run.status);
  const openArtifact=async(id:string,name:string)=>{try{const blob=await api.downloadArtifact(id);const url=URL.createObjectURL(blob);const anchor=document.createElement('a');anchor.href=url;anchor.download=name;anchor.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){setArtifactError(String(error));}};
  return <div className="lc-stack"><section className="lc-card"><div className="lc-toolbar"><strong>{t('liveRun')}</strong>{live.run&&<span className="badge badge-draft">{live.run.status} · {live.run.passed}/{live.run.total}</span>}{active&&<button className="btn btn-secondary btn-sm" onClick={()=>void api.cancelTestRun(live.run!.id).catch(reason=>setArtifactError(String(reason)))}>{t('runCancelled')}</button>}</div>{runId&&<Link className="lc-caption" to={`/runs/${runId}`}>{runId} · {t('openRun')}</Link>}
      <nav className="lc-tabs">{['live','results','network','console','steps','logs','artifacts'].map(key=><button key={key} className={tab===key?'selected':''} onClick={()=>setTab(key)}>{t(key==='live'?'browser':key)}</button>)}</nav>
      {(live.error||artifactError)&&<p className="lc-notice lc-error" role="alert">{live.error||artifactError}</p>}
    </section>
    {tab==='live'&&<>{live.run?<LiveBrowserPanel sessions={live.sessions} frames={live.frames} runStatus={live.run.status} streamStatus={live.streamStatus} streamError={live.error}/>:<section className="lc-card"><p className="lc-muted">{t('noRun')}</p>{projectId==='proj_golden_shop_v1'&&<><p className="lc-caption">{t('previewNotice')}</p><iframe title="Northstar Demo Shop" src="/api/demo-shop/index.html"/></>}</section>}</>}
    {tab==='results'&&<section className="lc-card">{live.run?.executions.map(item=><div className="lc-gap" key={item.id}><strong>{item.status}</strong><span>{item.nodeid}</span><small>{Math.round(item.duration_ms)} ms</small>{item.error_message&&<p>{item.error_message}</p>}</div>)}{!live.run?.executions.length&&<p>{t('noTelemetry')}</p>}{live.run?.failed&&<Link to="/failures" className="btn btn-secondary">{t('analysis')}</Link>}</section>}
    {['network','console','steps'].includes(tab)&&<section className="lc-card">{live.sessions.flatMap(session=>((session.page_evidence?.[({network:'network_logs',console:'console_logs',steps:'recent_steps'} as Record<string,string>)[tab]]??[]) as Record<string,unknown>[]).map((entry,index)=><details key={`${session.browser_session_id}:${index}`} className="lc-card"><summary>{String(entry.method??entry.action??entry.level??'')} · {String(entry.url??entry.locator??entry.text??'').slice(0,130)} · {String(entry.status??'')} {entry.duration_ms!==undefined&&`${entry.duration_ms} ms`}</summary><pre>{JSON.stringify(entry,null,2)}</pre>{typeof entry.file==='string'&&typeof entry.line==='number'&&<button className="btn btn-secondary" onClick={()=>onStep(entry.file as string,entry.line as number)}>{entry.file}:{entry.line}</button>}</details>))}{!live.sessions.length&&<p>{t('noTelemetry')}</p>}</section>}
    {tab==='logs'&&<section className="lc-card"><pre>{live.run?.log_output||t('noTelemetry')}</pre></section>}
    {tab==='artifacts'&&<section className="lc-card">{live.run?.external_artifacts?.map(artifact=><button key={artifact.id} className="lc-gap" onClick={()=>{const id=artifact.metadata_json?.artifact_id;if(typeof id==='string')void openArtifact(id,artifact.name);}}>{artifact.type} · {artifact.name}</button>)}{!live.run?.external_artifacts?.length&&<p>{t('noTelemetry')}</p>}</section>}
  </div>;
}
