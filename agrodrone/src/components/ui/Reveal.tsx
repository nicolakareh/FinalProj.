"use client";

import type { ReactNode } from "react";
import { motion } from "framer-motion";

type Props = {
  children: ReactNode;
  className?: string;
  /** Seconds to wait after entering view. Use for stagger. */
  delay?: number;
  /** Starting offset in px. */
  y?: number;
  /** Fraction of the element that must be visible before it reveals. */
  amount?: number;
  once?: boolean;
};

export const EASE_OUT = [0.25, 1, 0.5, 1] as const;

/**
 * Fade-and-rise on scroll. Fires once, fast, ease-out. Elements carry
 * `data-reveal` so a noscript rule in the layout can force them visible.
 */
export function Reveal({ children, className, delay = 0, y = 24, amount = 0.2, once = true }: Props) {
  return (
    <motion.div
      data-reveal=""
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once, amount, margin: "0px 0px -8% 0px" }}
      transition={{ duration: 0.55, ease: EASE_OUT, delay }}
    >
      {children}
    </motion.div>
  );
}
