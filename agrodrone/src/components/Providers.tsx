"use client";

import type { ReactNode } from "react";
import { MotionConfig, useReducedMotion } from "framer-motion";
import { ReactLenis } from "lenis/react";
import "lenis/dist/lenis.css";

/**
 * Smooth scroll (Lenis) and Framer Motion defaults. Under prefers-reduced-motion
 * Lenis tracks the input 1:1 (lerp 1) and Framer drops transform animations.
 */
export function Providers({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion();
  return (
    <MotionConfig reducedMotion="user" transition={{ duration: 0.4, ease: [0.25, 1, 0.5, 1] }}>
      <ReactLenis
        root
        options={{
          lerp: reduced ? 1 : 0.11,
          smoothWheel: !reduced,
          anchors: { offset: -56 },
          autoRaf: true,
        }}
      >
        {children}
      </ReactLenis>
    </MotionConfig>
  );
}
