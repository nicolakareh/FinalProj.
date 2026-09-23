"use client";

import { useState, useSyncExternalStore } from "react";
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

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-50 border-b transition-[background-color,border-color,color] duration-300 ease-out",
        solid ? "border-line/70 bg-paper/85 text-ink backdrop-blur-md" : "border-transparent bg-transparent text-paper",
      )}
    >
      <Container className="flex h-16 items-center justify-between">
        <a href="#top" className="rounded-sm focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-field" aria-label={`${site.name} home`}>
          <Wordmark />
        </a>

        <nav aria-label="Primary" className="hidden md:block">
          <ul className="flex items-center gap-8">
            {site.nav.links.map((link) => (
              <li key={link.href}>
                <a
                  href={link.href}
                  className={cn(
                    "relative text-[15px] font-medium transition-opacity duration-200 hover:opacity-100",
                    solid ? "opacity-80" : "opacity-85",
                  )}
                >
                  {link.label}
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
            className="inline-flex h-10 w-10 items-center justify-center rounded-full md:hidden"
            aria-expanded={open}
            aria-controls="mobile-menu"
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <Close /> : <Menu />}
          </button>
        </div>
      </Container>

      <div id="mobile-menu" hidden={!open} className="border-t border-line/70 bg-paper md:hidden">
        <Container className="flex flex-col gap-1 py-4">
          {site.nav.links.map((link) => (
            <a key={link.href} href={link.href} onClick={() => setOpen(false)} className="rounded-lg px-2 py-3 text-lg font-medium text-ink hover:bg-ink/5">
              {link.label}
            </a>
          ))}
          <Button href={site.nav.cta.href} onClick={() => setOpen(false)} className="mt-3 w-full sm:hidden">
            {site.nav.cta.label}
          </Button>
        </Container>
      </div>
    </header>
  );
}
