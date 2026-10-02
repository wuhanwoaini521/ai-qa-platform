import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';

export function ReadinessNotice() {
  const { t } = useTranslation('settings');
  const [limited, setLimited] = useState<string[]>([]);
  const [dismissed, setDismissed] = useState(false);
  useEffect(() => {
    let active = true;
    api.getSystemHealth().then((health) => { if (active) setLimited(health.components.filter((item) => item.status === 'error' || item.component === 'ai' && item.status !== 'ok').map((item) => item.component)); }).catch(() => { if (active) setLimited(['database']); });
    return () => { active = false; };
  }, []);
  if (dismissed || limited.length === 0) return null;
  return <div role="status" style={{ padding: '8px 16px', background: 'var(--warning-light)', fontSize: 12, display: 'flex', flexWrap: 'wrap', gap: 8 }}><span>{t('health.degraded')}: {limited.map((item) => t(`health.components.${item}`)).join(' · ')}</span><Link to="/settings">{t('health.title')}</Link><button className="btn btn-secondary btn-sm" type="button" onClick={() => setDismissed(true)}>{t('health.dismiss')}</button></div>;
}
