"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { site } from "@/content/site";
import { cn } from "@/lib/cn";
import { Container } from "@/components/ui/Container";
import { Button } from "@/components/ui/Button";
import { Wordmark } from "@/components/ui/Wordmark";
import { Close, Menu } from "@/components/ui/Icons";

const SCROLL_THRESHOLD = 32;

function subscribe(onChange: () => void) {
  window.addEventListener("scroll", onChange, { passive: true });
  return () => window.removeEventListener("scroll", onChange);
}

function useScrolled() {
  return useSyncExternalStore(
    subscribe,
    () => window.scrollY > SCROLL_THRESHOLD,
    () => false,
  );
}

/**
 * Fixed nav. Transparent with light text over the hero; once the page scrolls
 * it turns near-white with a blur and a hairline. The mobile menu forces the
 * solid state so the panel stays legible.
 */
export function Nav() {
  const scrolled = useScrolled();
  const [open, setOpen] = useState(false);
  const solid = scrolled || open;

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-50 border-b transition-[background-color,border-color,color] duration-300 ease-out",
        solid ? "border-line/70 bg-paper/85 text-ink backdrop-blur-md" : "border-transparent bg-transparent text-paper",
      )}
    >
      <Container className={cn("flex items-center justify-between transition-[height] duration-300 ease-out", solid ? "h-14" : "h-16")}>
        <a href="#top" className="rounded-sm focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-field" aria-label={`${site.name} home`}>
          <Wordmark />
        </a>

        <nav aria-label="Primary" className="hidden md:block">
          <ul className="flex items-center gap-8">
            {site.nav.links.map((link) => (
              <li key={link.href}>
                <a href={link.href} className="group relative inline-block py-1 text-[15px] font-medium opacity-85 transition-opacity duration-200 hover:opacity-100">
                  {link.label}
                  <span
                    aria-hidden="true"
                    className="absolute inset-x-0 -bottom-0.5 h-px origin-left scale-x-0 bg-current transition-transform duration-300 ease-out group-hover:scale-x-100"
                  />
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="flex items-center gap-2">
          <Button href={site.nav.cta.href} size="sm" variant={solid ? "primary" : "inverse"} className="hidden sm:inline-flex">
            {site.nav.cta.label}
          </Button>
          <button
            type="button"
            className="inline-flex h-10 w-10 items-center justify-center rounded-full transition-colors duration-200 hover:bg-current/10 md:hidden"
            aria-expanded={open}
            aria-controls="mobile-menu"
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <Close /> : <Menu />}
          </button>
        </div>
      </Container>

      <AnimatePresence>
        {open && (
          <motion.div
            id="mobile-menu"
            key="mobile-menu"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2, ease: [0.25, 1, 0.5, 1] }}
            className="border-t border-line/70 bg-paper md:hidden"
          >
            <Container className="flex flex-col gap-1 py-4">
              {site.nav.links.map((link, i) => (
                <motion.a
                  key={link.href}
                  href={link.href}
                  onClick={() => setOpen(false)}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.04 + i * 0.04, duration: 0.25 }}
                  className="rounded-lg px-2 py-3 text-lg font-medium text-ink transition-colors duration-200 hover:bg-ink/5"
                >
                  {link.label}
                </motion.a>
              ))}
              <Button href={site.nav.cta.href} onClick={() => setOpen(false)} className="mt-3 w-full sm:hidden">
                {site.nav.cta.label}
              </Button>
            </Container>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
