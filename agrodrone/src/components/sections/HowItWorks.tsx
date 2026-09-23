"use client";

import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";
import { site } from "@/content/site";
import { Container } from "@/components/ui/Container";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { Reveal, EASE_OUT } from "@/components/ui/Reveal";

const PLAN_PATH = "M48 48 H192 V68 H48 V88 H192 V108 H48";

/** Small animated illustration per step. Each one plays when it scrolls into view. */
function StepArt({ index }: { index: number }) {
  const reduced = useReducedMotion();
  const line = { fill: "none", stroke: "#0e0f0c", strokeWidth: 1.5, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  const inView = { once: true, amount: 0.6 };

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
          <motion.path
            {...line}
            stroke="#3f6b3a"
            strokeWidth="2"
            d="M48 44 L172 36 L196 92 L150 128 L64 118 Z"
            initial={{ pathLength: 0 }}
            whileInView={{ pathLength: 1 }}
            viewport={inView}
            transition={{ duration: 1.4, ease: EASE_OUT }}
          />
          {[
            [48, 44],
            [172, 36],
            [196, 92],
            [150, 128],
            [64, 118],
          ].map(([cx, cy], i) => (
            <motion.circle
              key={`${cx}-${cy}`}
              cx={cx}
              cy={cy}
              r="3.5"
              fill="#3f6b3a"
              initial={{ opacity: 0, scale: 0 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={inView}
              transition={{ delay: 0.25 * i, duration: 0.35, ease: EASE_OUT }}
              style={{ transformBox: "fill-box", transformOrigin: "center" }}
            />
          ))}
        </g>
      )}

      {index === 1 && (
        <g>
          <rect x="30" y="30" width="180" height="100" rx="8" fill="#fafaf7" stroke="#d9cfb8" />
          <path {...line} strokeOpacity="0.35" strokeDasharray="4 4" d={PLAN_PATH} />
          <motion.path
            {...line}
            stroke="#3f6b3a"
            strokeWidth="2"
            d={PLAN_PATH}
            initial={{ pathLength: 0 }}
            whileInView={{ pathLength: 1 }}
            viewport={inView}
            transition={reduced ? { duration: 0 } : { duration: 4, ease: "linear", repeat: Infinity, repeatDelay: 1.2 }}
          />
          <circle r="4" fill="#3f6b3a">
            {!reduced && <animateMotion dur="4s" begin="0s" repeatCount="indefinite" path={PLAN_PATH} calcMode="linear" />}
          </circle>
        </g>
      )}

      {index === 2 && (
        <g>
          <g {...line}>
            <circle cx="106" cy="46" r="4" />
            <circle cx="134" cy="46" r="4" />
            <circle cx="106" cy="66" r="4" />
            <circle cx="134" cy="66" r="4" />
            <path d="M109 49 131 63M131 49 109 63" />
          </g>
          <motion.path
            d="M100 80 L64 132 H176 L140 80 Z"
            fill="#3f6b3a"
            initial={{ fillOpacity: 0.08 }}
            animate={reduced ? { fillOpacity: 0.14 } : { fillOpacity: [0.08, 0.18, 0.08] }}
            transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
          />
          {[
            [104, 84, 80, 124],
            [120, 84, 120, 126],
            [136, 84, 160, 124],
          ].map(([x1, y1, x2, y2], i) => (
            <motion.line
              key={i}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke="#3f6b3a"
              strokeWidth="1.5"
              strokeLinecap="round"
              initial={{ pathLength: 0, opacity: 0 }}
              animate={reduced ? { pathLength: 1, opacity: 0.7 } : { pathLength: [0, 1, 1], opacity: [0, 0.8, 0] }}
              transition={{ duration: 1.6, repeat: Infinity, delay: i * 0.25, ease: "easeOut" }}
            />
          ))}
          <line x1="40" y1="134" x2="200" y2="134" stroke="#d9cfb8" />
        </g>
      )}

      {index === 3 && (
        <g>
          <rect x="30" y="26" width="180" height="108" rx="8" fill="#fafaf7" stroke="#d9cfb8" />
          {[
            [52, 30, 0.45],
            [80, 50, 0.6],
            [108, 40, 0.5],
            [136, 66, 1],
            [164, 56, 0.75],
          ].map(([x, h, o], i) => (
            <motion.rect
              key={x}
              x={x}
              width="18"
              rx="2"
              fill="#3f6b3a"
              fillOpacity={o}
              initial={{ height: 0, y: 116 }}
              whileInView={{ height: h, y: 116 - h }}
              viewport={inView}
              transition={{ delay: 0.12 * i, duration: 0.7, ease: EASE_OUT }}
            />
          ))}
          <line x1="46" y1="116" x2="194" y2="116" stroke="#0e0f0c" strokeOpacity="0.4" />
          <line x1="46" y1="42" x2="110" y2="42" stroke="#d9cfb8" strokeWidth="3" strokeLinecap="round" />
        </g>
      )}
    </svg>
  );
}

/**
 * Four steps. Desktop: the section pins while the row of cards slides
 * horizontally with scroll. Mobile and tablet: a plain stacked list.
 */
export function HowItWorks() {
  const { how } = site;
  const sectionRef = useRef<HTMLElement>(null);
  const trackRef = useRef<HTMLOListElement>(null);
  const [shift, setShift] = useState(0);
  const { scrollYProgress } = useScroll({ target: sectionRef, offset: ["start start", "end end"] });
  const x = useTransform(scrollYProgress, [0, 1], [0, -shift]);

  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;
    const ro = new ResizeObserver(() => {
      setShift(Math.max(0, track.scrollWidth - track.clientWidth));
    });
    ro.observe(track);
    return () => ro.disconnect();
  }, []);

  return (
    <section ref={sectionRef} id="how-it-works" className="section-pad relative scroll-mt-16 lg:h-[320vh] lg:py-0">
      <div className="lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col lg:justify-center lg:overflow-x-clip">
        <Container>
          <div className="flex items-end justify-between gap-6">
            <SectionHeader eyebrow={how.eyebrow} title={how.headline} lead={how.lead} />
            <p className="type-eyebrow hidden shrink-0 pb-2 text-ink-3 lg:block" aria-hidden="true">
              {how.scrollHint} ↓
            </p>
          </div>
        </Container>

        <Container className="section-gap">
          <motion.ol ref={trackRef} style={{ x }} className="grid gap-4 sm:grid-cols-2 lg:flex lg:gap-6">
            {how.steps.map((step, i) => (
              <li key={step.title} className="lg:w-[440px] lg:shrink-0">
                <Reveal delay={i * 0.06} className="h-full">
                  <div className="flex h-full flex-col rounded-2xl border border-line bg-paper p-4 transition-[border-color,transform,box-shadow] duration-300 ease-out hover:-translate-y-0.5 hover:border-ink/25 hover:shadow-[0_18px_40px_-28px_rgba(14,15,12,0.35)] sm:p-5">
                    <StepArt index={i} />
                    <div className="mt-5 flex items-baseline gap-3">
                      <span className="type-eyebrow text-field">0{i + 1}</span>
                      <h3 className="type-h3">{step.title}</h3>
                    </div>
                    <p className="mt-2 text-[15px] leading-relaxed text-ink-2">{step.body}</p>
                  </div>
                </Reveal>
              </li>
            ))}
          </motion.ol>
        </Container>

        <Container className="mt-10 hidden lg:block">
          <div className="flex items-center gap-4">
            <span className="type-eyebrow tabular-nums text-ink-3">01</span>
            <div className="h-px flex-1 bg-line">
              <motion.div className="h-full origin-left bg-ink" style={{ scaleX: scrollYProgress }} />
            </div>
            <span className="type-eyebrow tabular-nums text-ink-3">0{how.steps.length}</span>
          </div>
        </Container>
      </div>
    </section>
  );
}
