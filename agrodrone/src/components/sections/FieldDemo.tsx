"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useInView, useReducedMotion } from "framer-motion";
import { site, type DemoModeId } from "@/content/site";
import { cn } from "@/lib/cn";
import { estimateMinutes, formatMinutes, SETUP_MINUTES } from "@/lib/estimator";
import { Container } from "@/components/ui/Container";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { Reveal } from "@/components/ui/Reveal";

/** PLACEHOLDER: swath width shown in the readout. Set to the aircraft's real figure. */
const SWATH_METERS = 6;

const FIELD = { x: 40, y: 40, w: 720, h: 440, pad: 22 } as const;
const ACRES = { min: 10, max: 160, step: 10, initial: 80 } as const;
/** Flight time in the demo scales with passes but stays watchable. */
const SECONDS_PER_PASS = 0.8;
const MIN_SECONDS = 5;
const MAX_SECONDS = 14;

type Point = { x: number; y: number };
type Segment = { from: Point; to: Point; len: number; start: number; kind: "pass" | "turn"; pass: number };
type Status = "ready" | "flying" | "paused" | "done";

/** Serpentine plan: one pass per strip, alternating direction, joined by short turns. */
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
  const segments: Segment[] = [];
  let acc = 0;
  for (let i = 0; i < points.length - 1; i++) {
    const from = points[i];
    const to = points[i + 1];
    const len = Math.hypot(to.x - from.x, to.y - from.y);
    segments.push({ from, to, len, start: acc, kind: i % 2 === 0 ? "pass" : "turn", pass: Math.floor(i / 2) });
    acc += len;
  }
  const seconds = Math.min(MAX_SECONDS, Math.max(MIN_SECONDS, passes * SECONDS_PER_PASS));
  const d = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x} ${p.y}`).join(" ");
  return { passes, rowH, points, segments, length: acc, seconds, d };
}

type Plan = ReturnType<typeof buildPlan>;

/** Drone position and per-pass coverage (0..1) at a given progress (0..1). */
function sample(plan: Plan, progress: number) {
  const dist = Math.max(0, Math.min(1, progress)) * plan.length;
  let seg = plan.segments[plan.segments.length - 1];
  for (const s of plan.segments) {
    if (dist <= s.start + s.len) {
      seg = s;
      break;
    }
  }
  const t = seg.len === 0 ? 1 : Math.min(1, Math.max(0, (dist - seg.start) / seg.len));
  const pos = { x: seg.from.x + (seg.to.x - seg.from.x) * t, y: seg.from.y + (seg.to.y - seg.from.y) * t };
  const coverage = Array.from({ length: plan.passes }, (_, j) => {
    if (j < seg.pass) return 1;
    if (j > seg.pass) return 0;
    return seg.kind === "pass" ? t : 1;
  });
  const covered = coverage.reduce((a, b) => a + b, 0) / plan.passes;
  const heading = seg.kind === "pass" ? (seg.to.x > seg.from.x ? 1 : -1) : 0;
  return { pos, coverage, covered, currentPass: seg.pass, onPass: seg.kind === "pass", heading };
}

function mapApplication(mode: DemoModeId) {
  return mode === "seeding" ? "seeding" : mode === "pesticide" ? "protection" : "fertilizer";
}

export function FieldDemo() {
  const { demo } = site;
  const [mode, setMode] = useState<DemoModeId>(demo.modes[0].id);
  const [acres, setAcres] = useState<number>(ACRES.initial);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState<Status>("ready");
  const sliderId = useId();
  const clipId = `${sliderId.replace(/[^a-zA-Z0-9]/g, "")}-field`;
  const frameRef = useRef<HTMLDivElement>(null);
  const progressRef = useRef(0);
  const lastTickRef = useRef<number | null>(null);
  const inView = useInView(frameRef, { once: true, amount: 0.45 });
  const reduced = useReducedMotion();

  const plan = useMemo(() => buildPlan(acres), [acres]);
  const current = demo.modes.find((m) => m.id === mode) ?? demo.modes[0];
  const totalMinutes = estimateMinutes(acres, "other", mapApplication(mode));
  const flightMinutes = Math.max(0, totalMinutes - SETUP_MINUTES);
  const frame = sample(plan, progress);

  // Auto-start shortly after the frame scrolls into view. Reduced motion jumps
  // straight to the finished state.
  useEffect(() => {
    if (!inView) return;
    const id = window.setTimeout(() => {
      setStatus((s) => {
        if (s !== "ready") return s;
        if (reduced) {
          progressRef.current = 1;
          setProgress(1);
          return "done";
        }
        return "flying";
      });
    }, 350);
    return () => window.clearTimeout(id);
  }, [inView, reduced]);

  // Flight loop.
  useEffect(() => {
    if (status !== "flying") return;
    let raf = 0;
    const step = (now: number) => {
      if (lastTickRef.current == null) lastTickRef.current = now;
      const dt = (now - lastTickRef.current) / 1000;
      lastTickRef.current = now;
      const next = Math.min(1, progressRef.current + dt / plan.seconds);
      progressRef.current = next;
      setProgress(next);
      if (next >= 1) {
        setStatus("done");
        return;
      }
      raf = window.requestAnimationFrame(step);
    };
    raf = window.requestAnimationFrame(step);
    return () => {
      window.cancelAnimationFrame(raf);
      lastTickRef.current = null;
    };
  }, [status, plan.seconds]);

  function restart() {
    progressRef.current = 0;
    setProgress(0);
    setStatus("flying");
  }

  function togglePlay() {
    if (status === "flying") setStatus("paused");
    else if (status === "paused") setStatus("flying");
    else restart();
  }

  function changeAcres(next: number) {
    setAcres(next);
    progressRef.current = 0;
    setProgress(0);
    setStatus((s) => (s === "ready" ? "ready" : s === "paused" ? "paused" : "flying"));
  }

  const playLabel =
    status === "flying" ? demo.controls.pause : status === "paused" ? demo.controls.resume : status === "done" ? demo.controls.replay : demo.controls.play;
  const elapsed = formatMinutes(Math.round(flightMinutes * progress));
  const coveredPct = Math.round(frame.covered * 100);

  return (
    <section id="demo" className="section-pad scroll-mt-16 border-t border-line/70 bg-mist/60">
      <Container>
        <SectionHeader eyebrow={demo.eyebrow} title={demo.headline} lead={demo.lead} />

        <Reveal delay={0.1} amount={0.15} className="section-gap">
          <div ref={frameRef} className="overflow-hidden rounded-3xl border border-line bg-paper shadow-[0_1px_2px_rgba(14,15,12,0.04),0_24px_60px_-30px_rgba(14,15,12,0.25)]">
            {/* Frame header: mission status and elapsed time, like a live console. */}
            <div className="flex items-center justify-between border-b border-line px-5 py-3 text-sm">
              <div className="flex items-center gap-2.5">
                <span
                  className={cn(
                    "h-2 w-2 rounded-full",
                    status === "flying" && "bg-field animate-pulse",
                    status === "done" && "bg-field",
                    (status === "ready" || status === "paused") && "bg-ink-3",
                  )}
                  aria-hidden="true"
                />
                <span className="font-medium" aria-live="polite">
                  {demo.status[status]}
                </span>
              </div>
              <div className="tabular-nums text-ink-2">
                <span className="font-medium text-ink">{elapsed}</span> {demo.panel.elapsed}
              </div>
            </div>
            <div className="h-0.5 w-full bg-line/50" aria-hidden="true">
              <div className="h-full bg-field transition-[width] duration-100 ease-linear" style={{ width: `${coveredPct}%` }} />
            </div>

            <div className="grid lg:grid-cols-[1fr_320px]">
              {/* Field */}
              <div className="border-b border-line p-4 sm:p-6 lg:border-b-0 lg:border-r">
                <svg viewBox="0 0 800 520" className="h-auto w-full" role="img" aria-label={`Top-down field, ${plan.passes} passes, ${coveredPct}% covered with ${current.label.toLowerCase()}`}>
                  <defs>
                    <clipPath id={clipId}>
                      <rect x={FIELD.x} y={FIELD.y} width={FIELD.w} height={FIELD.h} rx="14" />
                    </clipPath>
                  </defs>
                  <rect x={FIELD.x} y={FIELD.y} width={FIELD.w} height={FIELD.h} rx="14" fill="#f1efe7" stroke="#d9cfb8" />
                  <g stroke="#d9cfb8" strokeOpacity="0.8">
                    {Array.from({ length: Math.floor(FIELD.h / 10) - 1 }, (_, i) => {
                      const y = FIELD.y + 10 * (i + 1);
                      return <line key={y} x1={FIELD.x + 8} y1={y} x2={FIELD.x + FIELD.w - 8} y2={y} strokeDasharray="3 5" />;
                    })}
                  </g>
                  {/* Coverage grows along each pass in the direction of travel. */}
                  <g clipPath={`url(#${clipId})`}>
                    {frame.coverage.map((c, i) => {
                      if (c <= 0) return null;
                      const forward = i % 2 === 0;
                      const width = (FIELD.w - 4) * c;
                      const x = forward ? FIELD.x + 2 : FIELD.x + FIELD.w - 2 - width;
                      return <rect key={i} x={x} y={FIELD.y + plan.rowH * i} width={width} height={plan.rowH} fill={current.color} fillOpacity="0.32" />;
                    })}
                  </g>
                  {/* Planned path, and the part already flown. */}
                  <path d={plan.d} fill="none" stroke="#0e0f0c" strokeOpacity="0.22" strokeWidth="1.5" strokeDasharray="5 5" strokeLinejoin="round" />
                  <path d={plan.d} fill="none" stroke="#0e0f0c" strokeOpacity="0.55" strokeWidth="1.5" strokeLinejoin="round" pathLength={1} strokeDasharray="1" strokeDashoffset={1 - progress} />
                  {/* Spray plume trails the drone while it is on a pass. */}
                  {frame.onPass && status !== "ready" && (
                    <ellipse
                      clipPath={`url(#${clipId})`}
                      cx={frame.pos.x - frame.heading * 22}
                      cy={frame.pos.y}
                      rx="24"
                      ry={Math.max(6, plan.rowH / 2 - 2)}
                      fill={current.color}
                      fillOpacity="0.28"
                    />
                  )}
                  {/* Drone */}
                  <g transform={`translate(${frame.pos.x} ${frame.pos.y})`}>
                    <circle r="16" fill={current.color} fillOpacity="0.18" />
                    <g fill="none" stroke="#0e0f0c" strokeWidth="1.6">
                      {[
                        [-7, -7],
                        [7, -7],
                        [-7, 7],
                        [7, 7],
                      ].map(([cx, cy]) => (
                        <g key={`${cx}${cy}`}>
                          <circle cx={cx} cy={cy} r="3.4" />
                          <line x1={cx - 3.4} y1={cy} x2={cx + 3.4} y2={cy} className={cn("rotor", status === "flying" && "animate-spin")} style={{ animationDuration: "0.35s" }} />
                        </g>
                      ))}
                      <path d="M-4.6 -4.6 4.6 4.6M4.6 -4.6 -4.6 4.6" strokeLinecap="round" />
                    </g>
                    <circle r="2.2" fill="#0e0f0c" />
                  </g>
                </svg>
              </div>

              {/* Controls and readout */}
              <div className="flex flex-col gap-7 p-5 sm:p-6">
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
                    onChange={(e) => changeAcres(Number(e.target.value))}
                    className="mt-3 w-full accent-field"
                  />
                </div>

                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={togglePlay}
                    className="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-full bg-ink px-4 text-sm font-medium text-paper transition-[background-color,transform] duration-200 ease-out hover:bg-field focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-field active:scale-[0.98]"
                  >
                    {playLabel}
                  </button>
                </div>

                <div>
                  <p className="type-eyebrow border-t border-line pt-4 text-ink-3">{demo.panel.title}</p>
                  <dl className="mt-1 divide-y divide-line border-b border-line text-sm">
                  <Row label={demo.panel.application} value={current.label} swatch={current.color} />
                  <Row label={demo.panel.field} value={`${acres} ac`} />
                  <Row label={demo.panel.passes} value={String(plan.passes)} />
                  <Row label={demo.panel.pass} value={status === "ready" ? "—" : `${Math.min(plan.passes, frame.currentPass + 1)} / ${plan.passes}`} />
                  <Row label={demo.panel.swath} value={`${SWATH_METERS} m`} />
                  <Row label={demo.panel.coverage} value={`${coveredPct}%`} />
                  <Row label={demo.panel.time} value={formatMinutes(totalMinutes)} />
                  </dl>
                </div>
              </div>
            </div>
          </div>
        </Reveal>
      </Container>
    </section>
  );
}

function Row({ label, value, swatch }: { label: string; value: string; swatch?: string }) {
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
