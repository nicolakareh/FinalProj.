"use client";

import { useId, useMemo, useState } from "react";
import { site, type DemoModeId } from "@/content/site";
import { cn } from "@/lib/cn";
import { estimateMinutes, formatMinutes } from "@/lib/estimator";
import { Container } from "@/components/ui/Container";
import { SectionHeader } from "@/components/ui/SectionHeader";

/** PLACEHOLDER: swath width shown in the readout. Set to the aircraft's real figure. */
const SWATH_METERS = 6;

const FIELD = { x: 40, y: 40, w: 720, h: 440, pad: 22 } as const;
const ACRES = { min: 10, max: 160, step: 10, initial: 80 } as const;

type Point = { x: number; y: number };

/** Serpentine plan: one pass per strip, alternating direction, joined at the ends. */
function buildPlan(acres: number) {
  const passes = Math.max(4, Math.min(22, Math.round(acres / 7)));
  const rowH = FIELD.h / passes;
  const left = FIELD.x + FIELD.pad;
  const right = FIELD.x + FIELD.w - FIELD.pad;
  const points: Point[] = [];
  for (let i = 0; i < passes; i++) {
    const y = FIELD.y + rowH * i + rowH / 2;
    const forward = i % 2 === 0;
    points.push({ x: forward ? left : right, y }, { x: forward ? right : left, y });
  }
  return { passes, rowH, points };
}

function mapApplication(mode: DemoModeId) {
  return mode === "seeding" ? "seeding" : mode === "pesticide" ? "protection" : "fertilizer";
}

export function FieldDemo() {
  const { demo } = site;
  const [mode, setMode] = useState<DemoModeId>(demo.modes[0].id);
  const [acres, setAcres] = useState<number>(ACRES.initial);
  const sliderId = useId();

  const plan = useMemo(() => buildPlan(acres), [acres]);
  const current = demo.modes.find((m) => m.id === mode) ?? demo.modes[0];
  const minutes = estimateMinutes(acres, "other", mapApplication(mode));

  // Static preview until the motion pass: the first few passes read as covered
  // and the drone sits at the end of the last covered pass.
  const previewPasses = Math.min(3, plan.passes);
  const dronePoint = plan.points[previewPasses * 2 - 1];
  const coveredPct = Math.round((previewPasses / plan.passes) * 100);
  const pathD = plan.points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x} ${p.y}`).join(" ");

  return (
    <section id="demo" className="section-pad scroll-mt-16 border-t border-line/70 bg-mist/60">
      <Container>
        <SectionHeader eyebrow={demo.eyebrow} title={demo.headline} lead={demo.lead} />

        <div className="mt-14 overflow-hidden rounded-3xl border border-line bg-paper shadow-[0_1px_2px_rgba(14,15,12,0.04),0_24px_60px_-30px_rgba(14,15,12,0.25)]">
          <div className="grid lg:grid-cols-[1fr_320px]">
            {/* Field */}
            <div className="border-b border-line p-4 sm:p-6 lg:border-b-0 lg:border-r">
              <svg viewBox="0 0 800 520" className="h-auto w-full" role="img" aria-label={`Top-down field with a ${plan.passes}-pass flight plan for ${current.label.toLowerCase()}`}>
                <rect x={FIELD.x} y={FIELD.y} width={FIELD.w} height={FIELD.h} rx="14" fill="#f1efe7" stroke="#d9cfb8" />
                {/* Crop rows */}
                <g stroke="#d9cfb8" strokeOpacity="0.8">
                  {Array.from({ length: Math.floor(FIELD.h / 10) - 1 }, (_, i) => {
                    const y = FIELD.y + 10 * (i + 1);
                    return <line key={y} x1={FIELD.x + 8} y1={y} x2={FIELD.x + FIELD.w - 8} y2={y} strokeDasharray="3 5" />;
                  })}
                </g>
                {/* Coverage strips */}
                <g>
                  {Array.from({ length: plan.passes }, (_, i) => (
                    <rect
                      key={i}
                      x={FIELD.x + 2}
                      y={FIELD.y + plan.rowH * i}
                      width={FIELD.w - 4}
                      height={plan.rowH}
                      fill={current.color}
                      fillOpacity={i < previewPasses ? 0.32 : 0}
                    />
                  ))}
                </g>
                {/* Flight path */}
                <path d={pathD} fill="none" stroke="#0e0f0c" strokeOpacity="0.35" strokeWidth="1.5" strokeDasharray="5 5" strokeLinejoin="round" />
                {/* Drone */}
                <g transform={`translate(${dronePoint.x} ${dronePoint.y})`}>
                  <circle r="16" fill={current.color} fillOpacity="0.18" />
                  <g fill="none" stroke="#0e0f0c" strokeWidth="1.6">
                    <circle cx="-7" cy="-7" r="3.2" />
                    <circle cx="7" cy="-7" r="3.2" />
                    <circle cx="-7" cy="7" r="3.2" />
                    <circle cx="7" cy="7" r="3.2" />
                    <path d="M-4.6 -4.6 4.6 4.6M4.6 -4.6 -4.6 4.6" strokeLinecap="round" />
                  </g>
                  <circle r="2.2" fill="#0e0f0c" />
                </g>
              </svg>
            </div>

            {/* Controls and readout */}
            <div className="flex flex-col gap-8 p-5 sm:p-6">
              <div>
                <p className="type-eyebrow text-ink-3">{demo.panel.application}</p>
                <div role="group" aria-label={demo.panel.application} className="mt-3 grid grid-cols-3 gap-1 rounded-full border border-line bg-mist p-1">
                  {demo.modes.map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      aria-pressed={mode === m.id}
                      onClick={() => setMode(m.id)}
                      className={cn(
                        "h-9 rounded-full text-sm font-medium transition-[background-color,color] duration-200 ease-out",
                        mode === m.id ? "bg-ink text-paper" : "text-ink-2 hover:text-ink",
                      )}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <div className="flex items-baseline justify-between">
                  <label htmlFor={sliderId} className="type-eyebrow text-ink-3">
                    {demo.sizeLabel}
                  </label>
                  <span className="text-sm font-medium tabular-nums">{acres} ac</span>
                </div>
                <input
                  id={sliderId}
                  type="range"
                  min={ACRES.min}
                  max={ACRES.max}
                  step={ACRES.step}
                  value={acres}
                  onChange={(e) => setAcres(Number(e.target.value))}
                  className="mt-3 w-full accent-field"
                />
              </div>

              <dl className="divide-y divide-line border-y border-line text-sm">
                <Row label={demo.panel.title} value="" heading />
                <Row label={demo.panel.application} value={current.label} swatch={current.color} />
                <Row label={demo.panel.field} value={`${acres} ac`} />
                <Row label={demo.panel.passes} value={String(plan.passes)} />
                <Row label={demo.panel.swath} value={`${SWATH_METERS} m`} />
                <Row label={demo.panel.coverage} value={`${coveredPct}%`} />
                <Row label={demo.panel.time} value={formatMinutes(minutes)} />
              </dl>
            </div>
          </div>
        </div>
      </Container>
    </section>
  );
}

function Row({ label, value, swatch, heading }: { label: string; value: string; swatch?: string; heading?: boolean }) {
  if (heading) {
    return (
      <div className="py-3">
        <dt className="type-eyebrow text-ink-3">{label}</dt>
      </div>
    );
  }
  return (
    <div className="flex items-center justify-between py-3">
      <dt className="text-ink-2">{label}</dt>
      <dd className="flex items-center gap-2 font-medium tabular-nums">
        {swatch && <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: swatch }} aria-hidden="true" />}
        {value}
      </dd>
    </div>
  );
}
