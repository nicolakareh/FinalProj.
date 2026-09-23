import { site } from "@/content/site";
import { Container } from "@/components/ui/Container";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { Reveal } from "@/components/ui/Reveal";

/** Qualitative two-column comparison. Numbers are added only when supplied. */
export function Comparison() {
  const { comparison } = site;
  const { columns } = comparison;
  const gridCols = "md:grid-cols-[1.1fr_1fr_1fr]";
  return (
    <section id="compare" className="section-pad scroll-mt-16">
      <Container>
        <SectionHeader eyebrow={comparison.eyebrow} title={comparison.headline} lead={comparison.lead} />
        <Reveal delay={0.1} amount={0.1} className="section-gap border-t border-line">
          <div className={`hidden border-b border-line md:grid ${gridCols}`} aria-hidden="true">
            <div className="type-eyebrow py-5 pr-6 text-ink-3">{columns.criterion}</div>
            <div className="type-eyebrow py-5 pr-6 text-field">{columns.drone}</div>
            <div className="type-eyebrow py-5 text-ink-3">{columns.tractor}</div>
          </div>
          <dl>
            {comparison.rows.map((row, i) => (
              <Reveal key={row.criterion} delay={0.05 * i} y={14} amount={0.4} className={`grid border-b border-line transition-colors duration-200 hover:bg-mist/50 ${gridCols}`}>
                <dt className="type-h3 pt-6 md:py-6 md:pr-6">{row.criterion}</dt>
                <dd className="py-4 text-[15px] leading-relaxed md:py-6 md:pr-6">
                  <span className="type-eyebrow mb-1 block text-field md:hidden">{columns.drone}</span>
                  {row.drone}
                </dd>
                <dd className="pb-6 pt-4 text-[15px] leading-relaxed text-ink-2 md:py-6">
                  <span className="type-eyebrow mb-1 block text-ink-3 md:hidden">{columns.tractor}</span>
                  {row.tractor}
                </dd>
              </Reveal>
            ))}
          </dl>
        </Reveal>
      </Container>
    </section>
  );
}
