import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowRight, Check } from 'lucide-react';
import type { ProjectKnowledge } from './types';

export function Journey({graph, active = '', analysisDone = false}: {graph: ProjectKnowledge; active?: string; analysisDone?: boolean}) {
  const {t} = useTranslation('lifecycle');
  const root = `/projects/${graph.project_id}`;
  const requirement = graph.nodes.find(n => n.kind==='requirement');
  const stages = [
    {id:'requirement', href:requirement?.href??`${root}/requirements`,done:!!graph.counts.requirement},
    {id:'analysis',href:`${requirement?.href??`${root}/requirements`}?tab=analysis`,done:analysisDone},
    {id:'design',href:`${requirement?.href??`${root}/requirements`}?tab=design`,done:!!graph.counts.design},
    {id:'case',href:`${root}/test-cases`,done:!!graph.counts.case},
    {id:'automation',href:`${root}/studio`,done:!!graph.counts.automated},
    {id:'run',href:graph.nodes.find(n=>n.kind==='run')?.href??'/runs',done:!!graph.counts.executed},
  ];
  const next = stages.find(stage => !stage.done) ?? stages[5];
  return <section className="lc-journey" aria-label={t('journey')}><nav className="lc-stepper">{stages.map((stage,index)=><Link key={stage.id} className={`${stage.done?'done':''} ${stage.id===active?'active':''}`} aria-current={stage.id===active?'step':undefined} to={stage.href}><i>{stage.done?<Check size={15}/>:index+1}</i><span>{t(`step.${stage.id}`)}</span></Link>)}</nav><div className="lc-next"><span>{t('nextAction')}</span><Link to={next.href}>{t(`step.${next.id}`)}<ArrowRight size={14}/></Link><span className="lc-muted">{t('contextKept')}</span></div></section>;
}
