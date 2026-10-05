import type { RuntimeSnapshot } from '../../types/runtime';
import { useTranslation } from 'react-i18next';
import { RuntimeArtifactActions } from './RuntimeArtifactActions';
export function RuntimeArtifacts({ snapshot }: { snapshot: RuntimeSnapshot }) {
  const { t } = useTranslation('runtime');
  return (
    <section className="rt-artifacts" aria-label={t('artifacts')}>
      {!snapshot.artifacts.length ? (
        <div className="rt-empty"><strong>{t('noArtifacts')}</strong>{snapshot.status === 'BLOCKED' && <p>{t('noArtifactsReason')}</p>}</div>
      ) : (
        snapshot.artifacts.map((artifact) => (
          <article className="rt-artifact" key={artifact.id}>
            <div>
              <h3>{artifact.name}</h3>
              <code>
                {artifact.type} · {artifact.source}
              </code>
            </div>
            <dl className="rt-artifact-info">
              <div>
                <dt>{t('createdAt')}</dt>
                <dd>
                  {artifact.created_at
                    ? new Date(artifact.created_at).toLocaleString()
                    : '—'}
                </dd>
              </div>
              <div>
                <dt>{t('size')}</dt>
                <dd>
                  {artifact.size_bytes == null
                    ? '—'
                    : `${artifact.size_bytes.toLocaleString()} bytes`}
                </dd>
              </div>
              <div>
                <dt>{t('step')}</dt>
                <dd>
                  {snapshot.steps.find((step) => step.id === artifact.step_id)
                    ?.key ?? '—'}
                </dd>
              </div>
              <div>
                <dt>{t('runCase')}</dt>
                <dd>
                  {artifact.test_run_id ?? '—'} / {artifact.case_id ?? '—'}
                </dd>
              </div>
            </dl>
            <RuntimeArtifactActions artifact={artifact} />
          </article>
        ))
      )}
    </section>
  );
}
