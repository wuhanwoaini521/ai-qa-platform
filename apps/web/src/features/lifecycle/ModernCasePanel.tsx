import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { TestCase } from '../../types';
import { KnowledgeDrawer } from './KnowledgeDrawer';
import './lifecycle.css';

export function ModernCasePanel({item}: {item: TestCase}) {
  const {t}=useTranslation('lifecycle');const [view,setView]=useState('flow');const [showKnowledge,setShowKnowledge]=useState(false);
  const model=item.test_model;if(!model)return null;
  const missing=[...model.missing,...(!model.oracles.length?[t('missingOracle')]:[]),...(!Object.keys(model.data).length?[t('missingData')]:[])];
  return <section className="lc-card"><div className="lc-header"><div><span className="lc-eyebrow">{model.display_id||item.id} · {model.technique}</span><h3>{t('testIntent')}</h3><p>{model.intent}</p></div><button className="btn btn-secondary" onClick={()=>setShowKnowledge(true)}>{t('whyCase')}</button></div>
    <div className="lc-chip-list">{Object.values(model.coverage).flat().map(id=><Link className="lc-chip" key={id} to={`/projects/${item.project_id}/requirements/${item.requirement_id}?tab=knowledge&node=${id}`}>{id}</Link>)}</div>
    <div className="lc-tabs"><button className={view==='flow'?'selected':''} onClick={()=>setView('flow')}>{t('flow')}</button><button className={view==='table'?'selected':''} onClick={()=>setView('table')}>{t('table')}</button><button className={view==='data'?'selected':''} onClick={()=>setView('data')}>{t('data')}</button></div>
    {view==='flow'&&<div className="lc-flow" style={{marginTop:16}}>{item.steps.map((step,index)=><div className="lc-flow-step" key={index}><i>{index+1}</i><span>{step}</span></div>)}<div className="lc-notice"><strong>{t('oracles')}</strong>{model.oracles.map((oracle,index)=><p key={index}>{oracle.kind} · {oracle.description} <small>{oracle.criterion_ids.join(', ')}</small></p>)}</div></div>}
    {view==='table'&&<div className="lc-table-scroll"><table className="data-table"><thead><tr><th>{t('actions')}</th><th>{t('oracles')}</th></tr></thead><tbody>{item.steps.map((step,index)=><tr key={index}><td>{index+1} · {step}</td><td>{index===item.steps.length-1?model.oracles.map(o=>o.description).join('；'):'—'}</td></tr>)}</tbody></table></div>}
    {view==='data'&&<><h3 style={{marginTop:16}}>{t('data')}</h3><pre>{JSON.stringify(model.data,null,2)}</pre><p className="lc-caption">{t('dataSource')}</p></>}
    <details open={!!missing.length}><summary>{t('readiness')} · {missing.length?t('needsInput'):t('readyForDraft')}</summary><p>{missing.length?missing.join('；'):t('draftNotVerified')}</p><p className="lc-caption">{t('evidence')} · {model.evidence.join(' · ')}</p>{item.binding&&<Link className="btn btn-primary" to={`/projects/${item.project_id}/studio/file/${item.binding.file_path}?caseId=${item.id}&target=${encodeURIComponent(item.binding.nodeid)}`}>{t('openAutomation')}</Link>}</details>
    {showKnowledge&&<KnowledgeDrawer projectId={item.project_id} entityId={item.id} onClose={()=>setShowKnowledge(false)}/>}
  </section>;
}
