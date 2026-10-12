# Fixes

1. **Mobile navigation width** — Browser review showed the pinned footer's tablet `width: 100%` rule squeezing the horizontal mobile navigation. Set the narrow-screen pinned area to content width and kept its controls compact. Rechecked `/tmp/aiqa-sidebar-mobile-final.png`.
2. **Toolbar context after selector relocation** — Removed the stale Workspace-only title-hiding rule so the page title remains visible in the toolbar. Rechecked `/tmp/aiqa-sidebar-desktop-verified.png`.

No backend, API, project data, or runtime changes were made.
