/**
 * Message for user-facing alerts and status lines.
 *
 * Mirrors the previous `err.message || err` interpolation for everything the API layer throws
 * (`fetch` failures and the `new Error(...)` raised by `request`).
 */
export const errorText = (err: unknown): string => {
  if (err instanceof Error) return err.message || String(err);
  return String(err);
};
