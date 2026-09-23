# Reference captures

Screenshots and structural notes of the two reference sites used to design the AgroDrone marketing site.

| Site | Role |
| --- | --- |
| https://droneshine.de | Benchmark to beat: layout, section order, imagery, clutter |
| https://birdeye.com | Interactivity reference: nav on scroll, section reveals, animated product UI, tabbed features, hover states |

`capture.mjs` loads each site at 1440px and 390px, dismisses cookie banners, screenshots the fold, the nav after scrolling, and the full page after a slow scroll (so scroll-triggered animations fire), then writes `*-notes.json` with headings, nav styles before/after scroll, detected animation libraries, tabs, videos, and page-builder fingerprints.

```bash
npm i -D playwright && npx playwright install chromium   # once
node reference/capture.mjs                               # writes into reference/
```

Note: the hosted Claude Code environment used for this project blocks both hosts by network policy, so the captures have to be produced from a machine that can reach them (or after the hosts are added to the environment's allowlist).
