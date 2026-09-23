"use client";

import { useId, useState, type KeyboardEvent } from "react";
import { site } from "@/content/site";
import { cn } from "@/lib/cn";
import { Container } from "@/components/ui/Container";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { MediaPlaceholder } from "@/components/ui/MediaPlaceholder";
import { Check } from "@/components/ui/Icons";

/**
 * Tabbed services. Arrow keys move between tabs; the panel swaps text and
 * media. Crossfade and the sliding indicator arrive with the motion pass.
 */
export function Services() {
  const { services } = site;
  const [active, setActive] = useState(0);
  const baseId = useId();
  const tab = services.tabs[active];

  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>) {
    const last = services.tabs.length - 1;
    let next = active;
    if (e.key === "ArrowRight") next = active === last ? 0 : active + 1;
    else if (e.key === "ArrowLeft") next = active === 0 ? last : active - 1;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = last;
    else return;
    e.preventDefault();
    setActive(next);
    document.getElementById(`${baseId}-tab-${next}`)?.focus();
  }

  return (
    <section id="services" className="section-pad scroll-mt-16 border-t border-line/70">
      <Container>
        <SectionHeader eyebrow={services.eyebrow} title={services.headline} lead={services.lead} />

        <div role="tablist" aria-label={services.eyebrow} className="mt-12 -mx-5 flex gap-1 overflow-x-auto border-b border-line px-5 sm:mx-0 sm:px-0">
          {services.tabs.map((t, i) => (
            <button
              key={t.id}
              id={`${baseId}-tab-${i}`}
              role="tab"
              type="button"
              aria-selected={i === active}
              aria-controls={`${baseId}-panel`}
              tabIndex={i === active ? 0 : -1}
              onClick={() => setActive(i)}
              onKeyDown={onKeyDown}
              className={cn(
                "-mb-px shrink-0 border-b-2 px-1 pb-4 pt-2 text-[15px] font-medium transition-colors duration-200 sm:px-2",
                i === active ? "border-ink text-ink" : "border-transparent text-ink-3 hover:text-ink",
                i > 0 && "ml-5 sm:ml-8",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div id={`${baseId}-panel`} role="tabpanel" aria-labelledby={`${baseId}-tab-${active}`} className="mt-12 grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
          <div>
            <h3 className="type-h3 text-2xl sm:text-3xl">{tab.title}</h3>
            <p className="type-lead mt-4 max-w-[40ch] text-ink-2">{tab.body}</p>
            <ul className="mt-8 space-y-4">
              {tab.bullets.map((b) => (
                <li key={b} className="flex items-start gap-3 text-[15px]">
                  <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-field-soft text-field">
                    <Check width={12} height={12} />
                  </span>
                  {b}
                </li>
              ))}
            </ul>
          </div>
          {/* Intended shot for each tab is documented next to `media` in content/site.ts. */}
          <MediaPlaceholder label={tab.media} className="aspect-[4/3] lg:aspect-[5/4]" />
        </div>
      </Container>
    </section>
  );
}
