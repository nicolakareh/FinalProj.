import { site } from "@/content/site";
import { Container } from "@/components/ui/Container";
import { SectionHeader } from "@/components/ui/SectionHeader";

/**
 * Small illustration per step. Static line art for now; each one animates in
 * the motion pass (boundary draws itself, path traces, spray pulses, bars grow).
 */
function StepArt({ index }: { index: number }) {
  const common = { fill: "none", stroke: "#0e0f0c", strokeWidth: 1.5, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg viewBox="0 0 240 160" className="h-auto w-full" aria-hidden="true">
      <rect x="0" y="0" width="240" height="160" rx="12" fill="#f1efe7" />
      {index === 0 && (
        <g>
          <g stroke="#d9cfb8">
            {[40, 80, 120].map((y) => (
              <line key={y} x1="20" y1={y} x2="220" y2={y} />
            ))}
            {[60, 100, 140, 180].map((x) => (
              <line key={x} x1={x} y1="20" x2={x} y2="140" />
            ))}
          </g>
          <path {...common} stroke="#3f6b3a" strokeWidth="2" d="M48 44 L172 36 L196 92 L150 128 L64 118 Z" />
          <circle cx="48" cy="44" r="3.5" fill="#3f6b3a" />
          <circle cx="172" cy="36" r="3.5" fill="#3f6b3a" />
          <circle cx="196" cy="92" r="3.5" fill="#3f6b3a" />
          <circle cx="150" cy="128" r="3.5" fill="#3f6b3a" />
          <circle cx="64" cy="118" r="3.5" fill="#3f6b3a" />
        </g>
      )}
      {index === 1 && (
        <g>
          <rect x="30" y="30" width="180" height="100" rx="8" fill="#fafaf7" stroke="#d9cfb8" />
          <path {...common} strokeDasharray="4 4" d="M48 48 H192 M192 48 V68 H48 M48 68 V88 H192 M192 88 V108 H48" />
          <path {...common} stroke="#3f6b3a" strokeWidth="2" d="M48 48 H120" />
          <circle cx="120" cy="48" r="4" fill="#3f6b3a" />
        </g>
      )}
      {index === 2 && (
        <g>
          <g {...common}>
            <circle cx="106" cy="46" r="4" />
            <circle cx="134" cy="46" r="4" />
            <circle cx="106" cy="66" r="4" />
            <circle cx="134" cy="66" r="4" />
            <path d="M109 49 131 63M131 49 109 63" />
          </g>
          <path d="M100 80 L64 132 H176 L140 80 Z" fill="#3f6b3a" fillOpacity="0.14" />
          <g stroke="#3f6b3a" strokeWidth="1.5" strokeLinecap="round" strokeOpacity="0.7">
            <line x1="104" y1="84" x2="80" y2="124" />
            <line x1="120" y1="84" x2="120" y2="126" />
            <line x1="136" y1="84" x2="160" y2="124" />
          </g>
          <line x1="40" y1="134" x2="200" y2="134" stroke="#d9cfb8" />
        </g>
      )}
      {index === 3 && (
        <g>
          <rect x="30" y="26" width="180" height="108" rx="8" fill="#fafaf7" stroke="#d9cfb8" />
          <g fill="#3f6b3a">
            <rect x="52" y="86" width="18" height="30" rx="2" fillOpacity="0.45" />
            <rect x="80" y="66" width="18" height="50" rx="2" fillOpacity="0.6" />
            <rect x="108" y="76" width="18" height="40" rx="2" fillOpacity="0.5" />
            <rect x="136" y="50" width="18" height="66" rx="2" />
            <rect x="164" y="60" width="18" height="56" rx="2" fillOpacity="0.75" />
          </g>
          <line x1="46" y1="116" x2="194" y2="116" stroke="#0e0f0c" strokeOpacity="0.4" />
          <line x1="46" y1="42" x2="110" y2="42" stroke="#d9cfb8" strokeWidth="3" strokeLinecap="round" />
        </g>
      )}
    </svg>
  );
}

/**
 * Four steps. Grid of cards for now; on desktop this becomes a horizontal,
 * scroll-pinned sequence in the motion pass, and stays stacked on mobile.
 */
export function HowItWorks() {
  const { how } = site;
  return (
    <section id="how-it-works" className="section-pad scroll-mt-16">
      <Container>
        <SectionHeader eyebrow={how.eyebrow} title={how.headline} lead={how.lead} />
        <ol className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {how.steps.map((step, i) => (
            <li key={step.title} className="flex flex-col rounded-2xl border border-line bg-paper p-4 sm:p-5">
              <StepArt index={i} />
              <div className="mt-5 flex items-baseline gap-3">
                <span className="type-eyebrow text-field">0{i + 1}</span>
                <h3 className="type-h3">{step.title}</h3>
              </div>
              <p className="mt-2 text-[15px] leading-relaxed text-ink-2">{step.body}</p>
            </li>
          ))}
        </ol>
      </Container>
    </section>
  );
}
