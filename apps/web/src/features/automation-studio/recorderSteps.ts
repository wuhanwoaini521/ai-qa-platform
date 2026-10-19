export type RecorderStepLocator = {
  kind?: string;
  value?: string;
  name?: string | null;
  nth?: number | null;
};

export type RecorderStep = {
  step_id?: string;
  action?: string;
  url?: string;
  frame_path?: string[];
  locator?: RecorderStepLocator | null;
  evidence_id?: string;
};

/** The recorder's captured locator, in the same shape `generate_python_case` turns into a call. */
export function locatorLabel(locator?: RecorderStepLocator | null): string {
  if (!locator?.kind || !locator.value) return '—';
  const name = locator.name ? ` (${locator.name})` : '';
  const nth = typeof locator.nth === 'number' ? ` [${locator.nth}]` : '';
  return `${locator.kind}: ${locator.value}${name}${nth}`;
}
