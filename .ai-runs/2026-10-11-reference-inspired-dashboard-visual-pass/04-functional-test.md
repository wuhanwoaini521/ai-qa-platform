# Functional Test

## Browser Smoke

Used a fresh headless Chrome profile against the running local application and the existing local development account. Only read-only page data was loaded; no AI calls, jobs, or business mutations were triggered.

- Dashboard rendered at 1440×900, 768×900, and 390×844.
- Document width matched viewport at all three sizes; no horizontal overflow observed.
- Desktop shows the compact attention rail and shared KPI surface; tablet uses two columns; phone stacks the attention list and KPIs.
- Programmatic keyboard-visible focus on an attention action reports a 2px solid focus outline.
- Dark theme rendered at 1440×900 with readable surfaces, borders, and status tones.
- Browser page errors: none. Console contained only Vite connection/HMR and React DevTools informational messages.

Screenshots: `/tmp/aiqa-design-after-dashboard-1440-final.png`, `/tmp/aiqa-design-after-dashboard-768.png`, `/tmp/aiqa-design-after-dashboard-390.png`, `/tmp/aiqa-design-after-dashboard-dark-1440.png`.
