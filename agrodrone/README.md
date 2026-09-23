# AgroDrone marketing site

Single-page marketing site for AgroDrone, a drone-based crop spraying service. Next.js App Router, TypeScript, Tailwind CSS v4, Framer Motion, Lenis.

```bash
npm install
npm run dev      # http://localhost:3000
npm run build && npm start
npm run lint
```

## Where things live

| Path | What it is |
| --- | --- |
| `src/content/site.ts` | Every word on the site. Edit copy here; components never hard-code text. |
| `src/lib/estimator.ts` | Acreage estimator. PLACEHOLDER rate constants at the top of the file. |
| `src/lib/coverage.ts` | ZIP-code lookup. PLACEHOLDER service-region prefixes at the top of the file. |
| `src/components/sections/` | One file per page section, in page order. |
| `src/components/ui/` | Buttons, headers, the media placeholder, icons, wordmark. |
| `src/app/globals.css` | Design tokens (colors, type scale, section rhythm). |
| `public/media/` | Video and image assets. See the README there for the intended shots. |

## Placeholders to replace before launch

- Stats values (`XX%`) and their sources in `content/site.ts`.
- Hero video and service images in `public/media/`.
- Rate constants in `lib/estimator.ts` and ZIP prefixes in `lib/coverage.ts`.
- Contact email, trust-row claims, and the licensing line in `content/site.ts`.
- The quote form logs to the console; wire it to a backend in `FinalCta.tsx`.
