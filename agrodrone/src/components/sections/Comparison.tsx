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
    <section id="compare" className="section-pad scroll-mt-16 bg-mist/60">
      <Container>
        <SectionHeader eyebrow={comparison.eyebrow} title={comparison.headline} lead={comparison.lead} />
        <Reveal delay={0.1} amount={0.1} className="mt-14 overflow-hidden rounded-3xl border border-line bg-paper">
          <div className={`hidden border-b border-line md:grid ${gridCols}`} aria-hidden="true">
            <div className="type-eyebrow p-6 text-ink-3">{columns.criterion}</div>
            <div className="type-eyebrow bg-field-soft/70 p-6 text-field">{columns.drone}</div>
            <div className="type-eyebrow p-6 text-ink-3">{columns.tractor}</div>
          </div>
          <dl>
            {comparison.rows.map((row, i) => (
              <Reveal key={row.criterion} delay={0.05 * i} y={14} amount={0.4} className={`grid border-b border-line transition-colors duration-200 last:border-b-0 hover:bg-mist/70 ${gridCols}`}>
                <dt className="type-h3 px-5 pt-5 md:p-6">{row.criterion}</dt>
                <dd className="bg-field-soft/70 px-5 py-4 text-[15px] leading-relaxed md:p-6">
                  <span className="type-eyebrow mb-1 block text-field md:hidden">{columns.drone}</span>
                  {row.drone}
                </dd>
                <dd className="px-5 pb-5 pt-4 text-[15px] leading-relaxed text-ink-2 md:p-6">
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
