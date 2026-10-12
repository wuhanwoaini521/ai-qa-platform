# Implementation

## Changes

- Moved the existing project selector from the toolbar into the sidebar header; kept project context scoped through `withProjectId` and updated selection after navigation.
- Added a desktop collapse/expand control with persisted preference (`ai-qa.sidebar-collapsed`), compact project selection, and accessible hover/focus labels in the icon rail.
- Restyled the sidebar as a separate rounded panel with neutral active state; grouped existing Platform destinations and pinned Settings/language controls at the bottom.
- Preserved the shared keyboard-search palette and its destinations. Added localized accessible labels for collapse/expand.
- Removed duplicate project-selection props/handler from `Header` and `AppLayout`; retained the selected project ID for the header's status query. `Tooltip` gained an opt-in desktop mode while retaining narrow-screen behavior.
- Updated responsive CSS for tablet/mobile layouts and theme-token compatibility. No routes, backend/API, database schema, runtime artifacts, or project data were changed. No reference-only account, billing, favorites, or help entries were fabricated.

## Browser-driven refinements

- A narrow-screen review exposed an overly wide pinned footer that squeezed the mobile navigation. Adjusted the compact-width rule so all existing nav items remain visible; rechecked the final mobile screenshot.
- Kept the Workspace page title visible after removing its project selector from the toolbar.

Implementation is complete; final checks and UI review are recorded in the following stages.
