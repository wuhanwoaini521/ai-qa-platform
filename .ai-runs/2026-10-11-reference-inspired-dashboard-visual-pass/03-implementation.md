# Implementation

## Changed

- `apps/web/src/index.css`
  - Set the desktop navigation rail to 240px; existing <=1150px compact rail remains 68px.
  - Compressed the attention queue into a horizontal summary/list at desktop, with two-column tablet and one-column phone layouts.
  - Consolidated KPI cards into a shared white metric surface with inline primary values and subtle separators; retained supporting counts and existing action buttons.
  - Kept the project overview as a quiet band and widened the trend/recent-run emphasis.
  - Used existing design tokens so light/dark palettes and focus treatment remain consistent.

No application markup, route, translation, API, or business logic changed.
