"use client";

import { useId, useState, type KeyboardEvent } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { site } from "@/content/site";
import { cn } from "@/lib/cn";
import { Container } from "@/components/ui/Container";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { MediaPlaceholder } from "@/components/ui/MediaPlaceholder";
import { Reveal, EASE_OUT } from "@/components/ui/Reveal";
import { Check } from "@/components/ui/Icons";

/**
 * Tabbed services. The underline slides between tabs (shared layout), and the
 * panel crossfades: old and new panels share one grid cell so height never jumps.
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

        <Reveal delay={0.1} y={12}>
          <div role="tablist" aria-label={services.eyebrow} className="section-gap -mx-5 flex gap-1 overflow-x-auto border-b border-line px-5 sm:mx-0 sm:px-0">
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
                  "relative shrink-0 px-1 pb-4 pt-2 text-[15px] font-medium transition-colors duration-200 sm:px-2",
                  i === active ? "text-ink" : "text-ink-3 hover:text-ink",
                  i > 0 && "ml-5 sm:ml-8",
                )}
              >
                {t.label}
                {i === active && (
                  <motion.span
                    layoutId={`${baseId}-indicator`}
                    className="absolute inset-x-0 -bottom-px h-0.5 bg-ink"
                    transition={{ type: "spring", stiffness: 520, damping: 42 }}
                  />
                )}
              </button>
            ))}
          </div>
        </Reveal>

        <div className="mt-10 grid lg:mt-12">
          <AnimatePresence initial={false}>
            <motion.div
              key={tab.id}
              id={`${baseId}-panel`}
              role="tabpanel"
              aria-labelledby={`${baseId}-tab-${active}`}
              className="col-start-1 row-start-1 grid items-center gap-10 lg:grid-cols-2 lg:gap-16"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0, pointerEvents: "auto" }}
              exit={{ opacity: 0, y: -6, pointerEvents: "none" }}
              transition={{ duration: 0.28, ease: EASE_OUT }}
            >
              <div>
                <h3 className="type-h3 text-2xl sm:text-3xl">{tab.title}</h3>
                <p className="type-lead mt-4 max-w-[40ch] text-ink-2">{tab.body}</p>
                <ul className="mt-8 space-y-4">
                  {tab.bullets.map((b, i) => (
                    <motion.li
                      key={b}
                      className="flex items-start gap-3 text-[15px]"
                      initial={{ opacity: 0, x: -6 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.06 + i * 0.05, duration: 0.3, ease: EASE_OUT }}
                    >
                      <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-field-soft text-field">
                        <Check width={12} height={12} />
                      </span>
                      {b}
                    </motion.li>
                  ))}
                </ul>
              </div>
              {/* Intended shot for each tab is documented next to `media` in content/site.ts. */}
              <MediaPlaceholder label={tab.media} className="aspect-[4/3] lg:aspect-[5/4]" />
            </motion.div>
          </AnimatePresence>
        </div>
      </Container>
    </section>
  );
}
