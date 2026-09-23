import { site } from "@/content/site";
import { Container } from "@/components/ui/Container";
import { Button } from "@/components/ui/Button";

/**
 * Placeholder for the hero video: a stylised field drawn in perspective, dark
 * ink ground with faint green rows converging on the horizon. Intended shot
 * (see content/site.ts): a spray drone crossing a crop field at golden hour,
 * low angle, slow lateral tracking, seamless loop.
 */
function HeroPlaceholder() {
  const vanishX = 800;
  const horizon = 330;
  const rays = Array.from({ length: 27 }, (_, i) => -760 + i * 130);
  const rows = [346, 366, 392, 426, 470, 526, 596, 684, 792];
  return (
    <svg className="absolute inset-0 h-full w-full" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <rect width="1600" height="900" fill="#0e0f0c" />
      <rect x="0" y={horizon} width="1600" height={900 - horizon} fill="#141a12" />
      <g stroke="#3f6b3a" strokeWidth="1.2">
        {rays.map((x) => (
          <line key={x} x1={vanishX} y1={horizon} x2={x} y2="900" strokeOpacity="0.32" />
        ))}
        {rows.map((y, i) => (
          <line key={y} x1="0" y1={y} x2="1600" y2={y} strokeOpacity={0.12 + i * 0.05} />
        ))}
      </g>
      <line x1="0" y1={horizon} x2="1600" y2={horizon} stroke="#d9cfb8" strokeOpacity="0.35" />
    </svg>
  );
}

export function Hero() {
  const { hero } = site;
  return (
    <section id="top" className="relative flex min-h-[100svh] items-end overflow-hidden bg-ink text-paper">
      <div className="absolute inset-0">
        {hero.video ? (
          <video
            className="absolute inset-0 h-full w-full object-cover"
            src={hero.video}
            poster={hero.videoPoster ?? undefined}
            autoPlay
            muted
            loop
            playsInline
            preload="metadata"
          />
        ) : (
          <HeroPlaceholder />
        )}
        {/* Legibility scrim only; not decorative. */}
        <div className="absolute inset-0 bg-ink/35" aria-hidden="true" />
      </div>

      <Container className="relative pb-16 pt-40 sm:pb-20 lg:pb-24">
        <h1 className="type-display max-w-[13ch]">{hero.headline}</h1>
        <p className="type-lead mt-6 max-w-[40ch] text-paper/80">{hero.subline}</p>
        <div className="mt-10 flex flex-wrap gap-3">
          <Button href={hero.primary.href} variant="inverse" size="lg" arrow>
            {hero.primary.label}
          </Button>
          <Button href={hero.secondary.href} variant="ghost-inverse" size="lg">
            {hero.secondary.label}
          </Button>
        </div>
        <ul className="mt-14 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-paper/65">
          {hero.trust.map((item, i) => (
            <li key={item} className="flex items-center gap-3">
              {i > 0 && <span aria-hidden="true" className="h-1 w-1 rounded-full bg-paper/40" />}
              {item}
            </li>
          ))}
        </ul>
      </Container>
    </section>
  );
}
