# UI Review

- **1440px:** navigation rail is modestly narrower; attention summary becomes a single low-height action rail; KPI values share a continuous metric surface; overview stays secondary; chart and recent runs are visible sooner. No clipped page edges.
- **768px:** navigation collapses to its existing icon rail; attention and KPI groups use two columns; chart and quick actions stack naturally.
- **390px:** existing mobile navigation remains intact; attention and KPIs stack with no horizontal overflow.
- **Dark theme:** token-based borders, canvas, status colors, chart, and text remain legible.
- **Accessibility:** existing semantic buttons and global `:focus-visible` treatment are unchanged; a visible 2px blue focus ring was confirmed on an attention action.
- No new animation or motion behavior was introduced.
