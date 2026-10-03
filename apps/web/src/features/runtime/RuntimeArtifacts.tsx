import type { RuntimeSnapshot } from '../../types/runtime';
import { RuntimeArtifactActions } from './RuntimeArtifactActions';
export function RuntimeArtifacts({ snapshot }: { snapshot: RuntimeSnapshot }) {
  return (
    <section className="rt-artifacts" aria-label="运行制品">
      {!snapshot.artifacts.length ? (
        <p className="rt-empty">此运行尚未产生制品</p>
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
                <dt>Created</dt>
                <dd>
                  {artifact.created_at
                    ? new Date(artifact.created_at).toLocaleString()
                    : '—'}
                </dd>
              </div>
              <div>
                <dt>Size</dt>
                <dd>
                  {artifact.size_bytes == null
                    ? '—'
                    : `${artifact.size_bytes.toLocaleString()} bytes`}
                </dd>
              </div>
              <div>
                <dt>Step</dt>
                <dd>
                  {snapshot.steps.find((step) => step.id === artifact.step_id)
                    ?.key ?? '—'}
                </dd>
              </div>
              <div>
                <dt>Run / Case</dt>
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
