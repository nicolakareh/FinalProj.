import { site } from "@/content/site";
import { Container } from "@/components/ui/Container";
import { SectionHeader } from "@/components/ui/SectionHeader";

/**
 * Three large numbers. The values are PLACEHOLDERS ("XX") until sourced
 * figures exist; edit them in content/site.ts and add the source. The count-up
 * animation arrives with the motion pass.
 */
export function Stats() {
  const { stats } = site;
  return (
    <section id="problem" className="section-pad scroll-mt-16">
      <Container>
        <SectionHeader eyebrow={stats.eyebrow} title={stats.headline} lead={stats.lead} />
        <dl className="mt-16 grid gap-10 border-t border-line pt-10 md:grid-cols-3 md:gap-8">
          {stats.items.map((item) => (
            <div key={item.label} className="md:border-l md:border-line md:pl-8 md:first:border-l-0 md:first:pl-0">
              <dd className="type-stat text-ink">
                {item.value}
                <span className="text-field">{item.suffix}</span>
              </dd>
              <dt className="mt-5 max-w-[24ch] text-base leading-snug text-ink-2">{item.label}</dt>
              {item.source && <p className="mt-2 text-xs text-ink-3">Source: {item.source}</p>}
            </div>
          ))}
        </dl>
      </Container>
    </section>
  );
}
