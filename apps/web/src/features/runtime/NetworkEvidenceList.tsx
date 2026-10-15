import { useTranslation } from 'react-i18next';
import { formatBrowserTimestamp } from './browserModel';

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function displayValue(value: unknown): string {
  if (typeof value === 'string') return value;
  try { return JSON.stringify(value, null, 2) ?? String(value); } catch { return String(value); }
}

export function NetworkEvidenceList({ entries }: { entries: unknown[] }) {
  const { t } = useTranslation('runtime');
  return (
    <div className="rt-network-list">
      <div className="rt-network-list-header" aria-hidden="true">
        <span />
        <span>{t('networkTime')}</span>
        <span>{t('networkMethod')}</span>
        <span>{t('networkUrl')}</span>
        <span>{t('networkStatus')}</span>
        <span>{t('networkDuration')}</span>
        <span>{t('networkDetails')}</span>
      </div>
      <ol>
        {entries.map((value, index) => {
          const entry = asRecord(value) ?? {};
          const request = asRecord(entry.request);
          const response = asRecord(entry.response);
          const status = entry.status ?? entry.status_code;
          const failure = entry.failure ?? entry.body_notice;
          const requestBody = request?.body;
          const responseBody = response?.body;
          const requestUnavailable = typeof requestBody === 'string' && requestBody.startsWith('[not captured:');
          const responseUnavailable = typeof responseBody === 'string' && responseBody.startsWith('[not captured:');
          const statusTone = typeof status === 'number' ? status >= 400 ? 'is-failed' : 'is-success' : failure ? 'is-failed' : '';
          return (
            <li key={`${String(entry.timestamp ?? '')}:${index}`}>
              <details>
                <summary aria-label={`${String(entry.method ?? 'HTTP')} ${String(entry.url || t('networkUrlMissing'))} ${t('networkStatus')} ${String(status ?? '—')}`}>
                  <time title={typeof entry.timestamp === 'string' ? entry.timestamp : undefined}>{formatBrowserTimestamp(entry.timestamp)}</time>
                  <code>{String(entry.method ?? 'HTTP')}</code>
                  <span className="rt-network-url" title={typeof entry.url === 'string' ? entry.url : undefined}>
                    {typeof entry.url === 'string' && entry.url ? entry.url : t('networkUrlMissing')}
                  </span>
                  <code className={statusTone}>{String(status ?? '—')}</code>
                  <span>{typeof entry.duration_ms === 'number' ? `${entry.duration_ms} ms` : '—'}</span>
                  <span className="rt-network-details-label">{t('networkDetails')}</span>
                </summary>
                <div className="rt-network-detail">
                  <section>
                    <h4>{t('networkRequest')}</h4>
                    {request ? <dl>
                      <div><dt>{t('networkContentType')}</dt><dd>{String(request.content_type || '—')}</dd></div>
                      <div><dt>{t('networkBody')}</dt><dd><pre>{requestUnavailable ? t('networkRequestBodyUnavailable') : requestBody == null ? t('networkNoRequestBody') : displayValue(requestBody)}</pre></dd></div>
                    </dl> : <p>{t('networkNoRequestDetails')}</p>}
                  </section>
                  <section>
                    <h4>{t('networkResponse')}</h4>
                    {response ? <dl>
                      <div><dt>{t('networkContentType')}</dt><dd>{String(response.content_type || '—')}</dd></div>
                      <div><dt>{t('networkBody')}</dt><dd><pre>{responseUnavailable ? t('networkResponseBodyUnavailable') : responseBody == null ? t('networkNoResponseBody') : displayValue(responseBody)}</pre></dd></div>
                    </dl> : <p>{t('networkNoResponseDetails')}</p>}
                    {failure != null && <p className="rt-network-failure"><strong>{t('networkFailure')}:</strong> {String(failure)}</p>}
                  </section>
                </div>
              </details>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
