import { site } from "@/content/site";
import { Container } from "@/components/ui/Container";
import { Reveal } from "@/components/ui/Reveal";

/**
 * Empty, labeled slot where partner and press logos will go. Deliberately
 * shows nothing until real logos exist; no fake social proof.
 */
export function ProofSlot() {
  if (!site.proof.enabled) return null;
  return (
    <section aria-label={site.proof.label} className="border-b border-line/70">
      <Container>
        <Reveal y={12} className="flex flex-col gap-5 py-8 sm:flex-row sm:items-center sm:gap-10">
          <p className="type-eyebrow shrink-0 text-ink-3">{site.proof.label}</p>
          <ul className="grid flex-1 grid-cols-3 gap-3 sm:grid-cols-5">
            {Array.from({ length: site.proof.slots }, (_, i) => (
              <li key={i} className={i >= 3 ? "hidden sm:block" : undefined}>
                <div className="h-10 rounded-md border border-dashed border-line" aria-hidden="true" />
              </li>
            ))}
          </ul>
        </Reveal>
      </Container>
    </section>
  );
}
