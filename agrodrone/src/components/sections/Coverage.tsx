"use client";

import { useId, useState, type FormEvent } from "react";
import { site } from "@/content/site";
import { cn } from "@/lib/cn";
import { checkZip, type CoverageStatus } from "@/lib/coverage";
import { Container } from "@/components/ui/Container";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { Button } from "@/components/ui/Button";
import { Reveal } from "@/components/ui/Reveal";

/**
 * PLACEHOLDER region map: an abstract service area over a dot grid. Swap the
 * polygon for the real region outline (or a tiled map) once the region is set.
 */
function RegionMap({ label }: { label: string }) {
  const dots: Array<[number, number]> = [];
  for (let y = 24; y <= 296; y += 16) for (let x = 24; x <= 376; x += 16) dots.push([x, y]);
  return (
    <div className="relative overflow-hidden rounded-3xl bg-paper">
      <svg viewBox="0 0 400 320" className="h-auto w-full" role="img" aria-label={label}>
        <g fill="#d9cfb8">
          {dots.map(([x, y]) => (
            <circle key={`${x}-${y}`} cx={x} cy={y} r="1.1" />
          ))}
        </g>
        <path
          d="M96 70 C140 40 220 44 268 66 C318 88 338 150 318 200 C300 246 240 270 186 262 C126 254 78 214 72 160 C68 122 70 88 96 70 Z"
          fill="#3f6b3a"
          fillOpacity="0.14"
          stroke="#3f6b3a"
          strokeWidth="1.5"
        />
        <circle cx="200" cy="158" r="4" fill="#3f6b3a" />
        <circle cx="200" cy="158" r="12" fill="none" stroke="#3f6b3a" strokeOpacity="0.4" />
      </svg>
      <span className="absolute bottom-3 left-3 rounded-full border border-line bg-paper/80 px-2.5 py-1 text-[11px] font-medium tracking-wide text-ink-2">{label}</span>
    </div>
  );
}

export function Coverage() {
  const { coverage } = site;
  const [zip, setZip] = useState("");
  const [result, setResult] = useState<{ status: CoverageStatus; zip: string } | null>(null);
  const inputId = useId();

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setResult(checkZip(zip));
  }

  const message = result ? coverage.results[result.status].replace("{zip}", result.zip) : null;

  return (
    <section id="coverage" className="section-pad scroll-mt-16 bg-mist/60">
      <Container>
        <div className="grid gap-12 lg:grid-cols-2 lg:items-center lg:gap-20">
          <div>
            <SectionHeader eyebrow={coverage.eyebrow} title={coverage.headline} lead={coverage.lead} />
            <Reveal delay={0.2}>
            <form onSubmit={onSubmit} className="mt-10 max-w-md" noValidate>
              <label htmlFor={inputId} className="type-eyebrow text-ink-3">
                {coverage.inputLabel}
              </label>
              <div className="mt-3 flex gap-2">
                <input
                  id={inputId}
                  type="text"
                  inputMode="numeric"
                  autoComplete="postal-code"
                  maxLength={5}
                  placeholder={coverage.inputPlaceholder}
                  value={zip}
                  onChange={(e) => {
                    setZip(e.target.value.replace(/\D/g, "").slice(0, 5));
                    setResult(null);
                  }}
                  className="h-12 w-full rounded-full border border-line bg-paper px-5 text-base tabular-nums outline-none transition-[border-color,box-shadow] duration-200 placeholder:text-ink-3 hover:border-ink/35 focus:border-field focus:ring-4 focus:ring-field/15"
                />
                <Button type="submit" size="lg">
                  {coverage.button}
                </Button>
              </div>
              <p
                role="status"
                aria-live="polite"
                className={cn(
                  "mt-4 min-h-6 text-[15px] leading-relaxed",
                  result?.status === "served" && "text-field",
                  result?.status === "soon" && "text-ink-2",
                  result?.status === "invalid" && "text-ink-2",
                )}
              >
                {message}
              </p>
            </form>
            </Reveal>
          </div>
          <Reveal delay={0.1} amount={0.3}>
            <RegionMap label={coverage.mapLabel} />
          </Reveal>
        </div>
      </Container>
    </section>
  );
}
