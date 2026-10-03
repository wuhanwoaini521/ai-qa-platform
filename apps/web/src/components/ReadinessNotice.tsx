import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import { api } from '../api/client';

/** One-line system notice. It reports degraded components without taking over the page. */
export function ReadinessNotice() {
  const { t } = useTranslation('settings');
  const [limited, setLimited] = useState<string[]>([]);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .getSystemHealth()
      .then((health) => {
        if (active) {
          setLimited(
            health.components
              .filter(
                (item) =>
                  item.status === 'error' ||
                  (item.component === 'ai' && item.status !== 'ok'),
              )
              .map((item) => item.component),
          );
        }
      })
      .catch(() => {
        if (active) setLimited(['database']);
      });
    return () => {
      active = false;
    };
  }, []);

  if (dismissed || limited.length === 0) return null;

  return (
    <div className="notice-strip" role="status">
      <span className="status-dot is-queued" />
      <span className="notice-strip-text">
        {t('health.degraded')}:{' '}
        {limited.map((item) => t(`health.components.${item}`)).join(' · ')}
      </span>
      <Link className="notice-strip-link" to="/settings">
        {t('health.title')}
      </Link>
      <button
        className="icon-btn"
        type="button"
        aria-label={t('health.dismiss')}
        title={t('health.dismiss')}
        onClick={() => setDismissed(true)}
      >
        <X size={14} strokeWidth={1.7} />
      </button>
    </div>
  );
}
