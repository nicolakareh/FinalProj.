import { site } from "@/content/site";
import type { Media } from "@/lib/media";
import { Container } from "@/components/ui/Container";
import { Button } from "@/components/ui/Button";
import { ArrowRight } from "@/components/ui/Icons";
import { DroneDrawing } from "@/components/ui/DroneDrawing";

/**
 * Fallback for the hero footage: a stylised field in perspective with a
 * technical drawing of the aircraft over it. Replaced automatically by
 * public/media/hero.mp4 (with hero-poster.jpg) once those files exist.
 * Intended shot: a spray drone crossing a crop field at golden hour, low angle,
 * slow lateral tracking, 8 to 12 s seamless loop, no audio.
 */
function HeroFallback() {
  const vanishX = 800;
  const horizon = 330;
  const rays = Array.from({ length: 27 }, (_, i) => -760 + i * 130);
  const rows = [346, 366, 392, 426, 470, 526, 596, 684, 792];
  return (
    <>
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <rect width="1600" height="900" fill="#0e0f0c" />
        <g className="hero-drift">
          <rect x="-200" y={horizon} width="2000" height={900 - horizon} fill="#131812" />
          <g stroke="#3f6b3a" strokeWidth="1.2">
            {rays.map((x) => (
              <line key={x} x1={vanishX} y1={horizon} x2={x} y2="900" strokeOpacity="0.26" />
            ))}
            {rows.map((y, i) => (
              <line key={y} x1="-200" y1={y} x2="1800" y2={y} strokeOpacity={0.1 + i * 0.04} />
            ))}
          </g>
          <line x1="-200" y1={horizon} x2="1800" y2={horizon} stroke="#d9cfb8" strokeOpacity="0.3" />
        </g>
      </svg>
      <div className="rise-block absolute right-[-10%] top-[6%] w-[92%] text-paper/50 sm:right-[-6%] sm:top-[8%] sm:w-[70%] sm:text-paper/70 lg:right-[-2%] lg:top-[6%] lg:w-[58%]" style={{ animationDelay: "0.5s" }}>
        <DroneDrawing className="rotate-[-6deg]" />
      </div>
    </>
  );
}

/** Entrance timing (seconds). Words rise first, then the rest in order. */
const WORD_DELAY = 0.1;
const WORD_STEP = 0.06;

export function Hero({ media }: { media: Media }) {
  const { hero } = site;
  const words = hero.headline.split(" ");
  const afterWords = WORD_DELAY + words.length * WORD_STEP;
  return (
    <section id="top" className="relative flex min-h-[100svh] items-end overflow-hidden bg-ink text-paper">
      <div className="absolute inset-0">
        {media.heroVideo ? (
          <video className="absolute inset-0 h-full w-full object-cover" src={media.heroVideo} poster={media.heroPoster ?? undefined} autoPlay muted loop playsInline preload="metadata" />
        ) : media.heroPoster ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={media.heroPoster} alt="" className="absolute inset-0 h-full w-full object-cover" fetchPriority="high" />
        ) : (
          <HeroFallback />
        )}
        {/* Legibility scrim, stronger at the bottom where the copy sits. */}
        <div className="absolute inset-0 bg-[linear-gradient(to_top,rgba(14,15,12,0.72)_0%,rgba(14,15,12,0.25)_45%,rgba(14,15,12,0.1)_100%)]" aria-hidden="true" />
      </div>

      <Container className="relative pb-14 pt-40 sm:pb-16 lg:pb-20">
        <h1 className="type-display max-w-[12ch]">
          {words.map((w, i) => (
            <span key={`${w}-${i}`} className="inline-block overflow-hidden pb-[0.08em] align-bottom">
              <span className="rise-word inline-block" style={{ animationDelay: `${WORD_DELAY + i * WORD_STEP}s` }}>
                {w}
                {i < words.length - 1 ? " " : ""}
              </span>
            </span>
          ))}
        </h1>
        <p className="rise-block type-lead mt-6 max-w-[38ch] text-paper/75" style={{ animationDelay: `${afterWords + 0.1}s` }}>
          {hero.subline}
        </p>
        <div className="rise-block mt-9 flex flex-col gap-4 sm:flex-row sm:items-center sm:gap-7" style={{ animationDelay: `${afterWords + 0.2}s` }}>
          <Button href={hero.primary.href} variant="inverse" size="lg" arrow className="w-full sm:w-auto">
            {hero.primary.label}
          </Button>
          <a href={hero.secondary.href} className="group inline-flex items-center gap-2 self-start text-[15px] font-medium text-paper/85 transition-colors duration-200 hover:text-paper sm:self-auto">
            {hero.secondary.label}
            <ArrowRight className="transition-transform duration-200 ease-out group-hover:translate-x-0.5" />
          </a>
        </div>
        <div className="rise-block mt-14 flex items-end justify-between gap-6" style={{ animationDelay: `${afterWords + 0.3}s` }}>
          <ul className="flex flex-wrap items-center gap-x-3 gap-y-2 text-[13px] text-paper/55">
            {hero.trust.map((item, i) => (
              <li key={item} className="flex items-center gap-3">
                {i > 0 && <span aria-hidden="true" className="h-1 w-1 rounded-full bg-paper/35" />}
                {item}
              </li>
            ))}
          </ul>
          <a href="#problem" className="type-eyebrow hidden shrink-0 items-center gap-2 text-paper/50 transition-colors duration-200 hover:text-paper sm:inline-flex" aria-label={hero.scrollCue}>
            {hero.scrollCue}
            <span aria-hidden="true" className="block h-8 w-px bg-current" />
          </a>
        </div>
      </Container>
    </section>
  );
}
