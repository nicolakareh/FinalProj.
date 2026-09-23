"use client";

import { useEffect, useRef, useState } from "react";
import { animate, useInView, useReducedMotion } from "framer-motion";

type Props = { value: string; duration?: number; className?: string };

/**
 * Counts from 0 to `value` when scrolled into view. Non-numeric values (the
 * "XX" placeholders) render as-is, so the animation only appears once real
 * figures are in the content file.
 */
export function CountUp({ value, duration = 1.4, className }: Props) {
  const target = Number(value);
  const numeric = value.trim() !== "" && Number.isFinite(target);
  const decimals = numeric ? (value.split(".")[1] ?? "").length : 0;
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "0px 0px -15% 0px" });
  const reduced = useReducedMotion();
  const [display, setDisplay] = useState(numeric ? (0).toFixed(decimals) : value);

  useEffect(() => {
    if (!numeric || !inView) return;
    const controls = animate(0, target, {
      duration: reduced ? 0 : duration,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => setDisplay(v.toFixed(decimals)),
    });
    return () => controls.stop();
  }, [inView, numeric, target, duration, reduced, decimals]);

  return (
    <span ref={ref} className={className}>
      {display}
    </span>
  );
}
