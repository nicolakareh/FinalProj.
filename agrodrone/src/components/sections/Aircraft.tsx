import { site } from "@/content/site";
import type { Media } from "@/lib/media";
import { Container } from "@/components/ui/Container";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { Reveal } from "@/components/ui/Reveal";
import { DroneDrawing } from "@/components/ui/DroneDrawing";

/**
 * Full-bleed dark band for the aircraft. With public/media/aircraft.jpg in
 * place the photo fills the section; until then a technical drawing carries it.
 * Intended shot: the aircraft on the ground at dawn, three-quarter view, field
 * behind, or a low aerial of it mid-pass.
 */
export function Aircraft({ media }: { media: Media }) {
  const { aircraft } = site;
  const photo = media.aircraft;
  return (
    <section id="aircraft" className="relative scroll-mt-16 overflow-hidden bg-ink text-paper">
      {photo ? (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={photo}
            srcSet={media.aircraftSmall ? `${media.aircraftSmall} 1200w, ${photo} 2400w` : undefined}
            sizes="100vw"
            alt=""
            className="absolute inset-0 h-full w-full object-cover"
            loading="lazy"
            decoding="async"
          />
          <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(14,15,12,0.85)_0%,rgba(14,15,12,0.55)_50%,rgba(14,15,12,0.35)_100%)]" aria-hidden="true" />
        </>
      ) : null}

      <Container className="section-pad relative">
        <div className="grid gap-14 lg:grid-cols-[1fr_1.1fr] lg:items-center lg:gap-10">
          <div>
            <SectionHeader eyebrow={aircraft.eyebrow} title={aircraft.headline} lead={aircraft.lead} tone="dark" />
            <Reveal delay={0.2} y={10}>
              <p className="mt-8 text-sm text-paper/50">{aircraft.model}</p>
            </Reveal>
          </div>
          {!photo && (
            <Reveal delay={0.15} amount={0.3} className="text-paper/80">
              <DroneDrawing className="mx-auto max-w-[640px]" />
              <p className="mt-2 text-center text-[11px] tracking-wide text-paper/40">Placeholder · {aircraft.media}</p>
            </Reveal>
          )}
        </div>

        <ul className="mt-16 grid gap-8 border-t border-paper/15 pt-10 sm:grid-cols-3 sm:gap-6">
          {aircraft.points.map((pt, i) => (
            <li key={pt.title}>
              <Reveal delay={0.1 + i * 0.08} y={14}>
                <h3 className="text-lg font-medium">{pt.title}</h3>
                <p className="mt-2 max-w-[30ch] text-[15px] leading-relaxed text-paper/60">{pt.body}</p>
              </Reveal>
            </li>
          ))}
        </ul>
      </Container>
    </section>
  );
}
