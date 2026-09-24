"use client";

import { useEffect, useRef } from "react";

type Props = { src: string };

/**
 * Hero background video that stays out of the way of first paint: nothing is
 * fetched until the page has loaded, and only on wide screens, with motion
 * allowed, and without a data-saver preference. Everyone else keeps the
 * responsive poster image rendered behind this element. No poster attribute
 * here on purpose: it would fetch the full-size still a second time.
 */
export function HeroVideo({ src }: Props) {
  const ref = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = ref.current;
    if (!video) return;
    const wide = window.matchMedia("(min-width: 768px)").matches;
    const motionOk = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const saveData = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData === true;
    if (!wide || !motionOk || saveData) return;

    let cancelled = false;
    const start = () => {
      if (cancelled) return;
      video.src = src;
      video.load();
      video.play().catch(() => {
        /* autoplay refused; poster stays */
      });
    };
    if (document.readyState === "complete") {
      const id = window.setTimeout(start, 400);
      return () => {
        cancelled = true;
        window.clearTimeout(id);
      };
    }
    window.addEventListener("load", start, { once: true });
    return () => {
      cancelled = true;
      window.removeEventListener("load", start);
    };
  }, [src]);

  return (
    <video
      ref={ref}
      className="absolute inset-0 h-full w-full object-cover object-[68%_40%] sm:object-center"
      muted
      loop
      playsInline
      preload="none"
      aria-hidden="true"
      tabIndex={-1}
    />
  );
}
