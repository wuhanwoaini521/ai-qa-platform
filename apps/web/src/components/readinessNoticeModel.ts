/** Which components genuinely limit capability, for the one-line readiness notice.
 *
 * A probe timeout only means availability was not confirmed in time, so it must not be
 * reported as a lost capability: the platform still allows the AI request to run to its
 * own timeout. Only a broken component (error) or an AI component that is really not
 * available (simulation, unconfigured, failed probe) limits what the user can do.
 */
export function limitedCapabilityComponents(
  components: { component: string; status: string; operational_state?: string | null }[],
): string[] {
  return components
    .filter(
      (item) =>
        item.status === 'error' ||
        (item.component === 'ai' && item.status !== 'ok' && item.operational_state !== 'PROBE_TIMEOUT'),
    )
    .map((item) => item.component);
}
