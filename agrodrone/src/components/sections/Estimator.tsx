"use client";

import { useId, useState } from "react";
import { site } from "@/content/site";
import { cn } from "@/lib/cn";
import { estimateMinutes, formatMinutes, type ApplicationId, type CropId } from "@/lib/estimator";
import { Container } from "@/components/ui/Container";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { Button } from "@/components/ui/Button";
import { Reveal } from "@/components/ui/Reveal";

export const PREFILL_EVENT = "agrodrone:prefill";

const fieldClass =
  "h-12 w-full rounded-xl border border-line bg-paper px-4 text-base text-ink outline-none transition-[border-color,box-shadow] duration-200 placeholder:text-ink-3 hover:border-ink/35 focus:border-field focus:ring-4 focus:ring-field/15";

/**
 * Acreage estimator. Rates are PLACEHOLDER constants at the top of
 * lib/estimator.ts. Output is labeled as an estimate, never a price.
 */
export function Estimator() {
  const { estimator } = site;
  const [acres, setAcres] = useState("120");
  const [crop, setCrop] = useState<CropId>(estimator.crops[0].id);
  const [application, setApplication] = useState<ApplicationId>(estimator.applications[0].id);
  const acresId = useId();
  const cropId = useId();

  const acresNum = Number(acres);
  const minutes = estimateMinutes(acresNum, crop, application);
  const valid = minutes > 0;

  function requestPricing() {
    window.dispatchEvent(new CustomEvent(PREFILL_EVENT, { detail: { acres: valid ? acresNum : undefined } }));
  }

  return (
    <section id="estimator" className="section-pad scroll-mt-16">
      <Container>
        <SectionHeader eyebrow={estimator.eyebrow} title={estimator.headline} lead={estimator.lead} />

        <div className="section-gap grid gap-4 lg:grid-cols-[1fr_1fr]">
          <Reveal delay={0.05} amount={0.2}>
          <form className="h-full rounded-3xl bg-mist/70 p-5 sm:p-8" onSubmit={(e) => e.preventDefault()}>
            <div className="grid gap-6">
              <div>
                <label htmlFor={acresId} className="type-eyebrow text-ink-3">
                  {estimator.acresLabel}
                </label>
                <input
                  id={acresId}
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={100000}
                  value={acres}
                  onChange={(e) => setAcres(e.target.value)}
                  className={cn(fieldClass, "mt-3")}
                />
              </div>
              <div>
                <label htmlFor={cropId} className="type-eyebrow text-ink-3">
                  {estimator.cropLabel}
                </label>
                <select id={cropId} value={crop} onChange={(e) => setCrop(e.target.value as CropId)} className={cn(fieldClass, "mt-3 appearance-none bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2216%22 height=%2216%22 fill=%22none%22 stroke=%22%2355584f%22 stroke-width=%221.75%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22><path d=%22M4 6l4 4 4-4%22/></svg>')] bg-[length:16px_16px] bg-[position:right_1rem_center] bg-no-repeat pr-10")}>
                  {estimator.crops.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <p className="type-eyebrow text-ink-3">{estimator.applicationLabel}</p>
                <div role="group" aria-label={estimator.applicationLabel} className="mt-3 grid grid-cols-3 gap-1 rounded-full border border-line bg-mist p-1">
                  {estimator.applications.map((a) => (
                    <button
                      key={a.id}
                      type="button"
                      aria-pressed={application === a.id}
                      onClick={() => setApplication(a.id)}
                      className={cn(
                        "h-10 rounded-full px-2 text-sm font-medium transition-[background-color,color] duration-200 ease-out",
                        application === a.id ? "bg-ink text-paper" : "text-ink-2 hover:text-ink",
                      )}
                    >
                      <span className="sm:hidden">{a.short}</span>
                      <span className="hidden sm:inline">{a.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </form>
          </Reveal>

          <Reveal delay={0.15} amount={0.2}>
          <div className="flex h-full flex-col justify-between rounded-3xl bg-ink p-6 text-paper sm:p-8">
            <div>
              <div className="flex items-center justify-between">
                <p className="type-eyebrow text-paper/60">{estimator.resultLabel}</p>
                <span className="rounded-full border border-paper/20 px-2.5 py-1 text-[11px] font-medium tracking-wide text-paper/70">{estimator.resultBadge}</span>
              </div>
              <p className="mt-6 text-[clamp(3rem,2rem+4vw,5.5rem)] font-semibold leading-none tracking-[-0.04em] tabular-nums" aria-live="polite">
                {valid ? formatMinutes(minutes) : "—"}
              </p>
              <p className="mt-6 max-w-[36ch] text-sm leading-relaxed text-paper/60">{estimator.disclaimer}</p>
            </div>
            <div className="mt-10">
              <Button href="#quote" variant="inverse" size="lg" arrow onClick={requestPricing}>
                {estimator.cta}
              </Button>
            </div>
          </div>
          </Reveal>
        </div>
      </Container>
    </section>
  );
}
