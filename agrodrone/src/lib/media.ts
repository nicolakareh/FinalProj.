import fs from "node:fs";
import path from "node:path";

/**
 * Server-side media lookup. Drop a file into public/media with one of the
 * names below and it is picked up on the next build with no config change.
 * Missing files return null and the component renders its fallback.
 *
 * Only import this from server components (page.tsx and friends).
 */
const FILES = {
  heroVideo: "media/hero.mp4",
  heroPoster: "media/hero-poster.jpg",
  heroPosterSmall: "media/hero-poster-1200.jpg",
  aircraft: "media/aircraft.jpg",
  aircraftSmall: "media/aircraft-1200.jpg",
  serviceFertilizer: "media/service-fertilizer.jpg",
  serviceProtection: "media/service-protection.jpg",
  serviceSeeding: "media/service-seeding.jpg",
  serviceMapping: "media/service-mapping.jpg",
} as const;

export type MediaKey = keyof typeof FILES;
export type Media = Record<MediaKey, string | null>;

function publicUrl(rel: string): string | null {
  if (!fs.existsSync(path.join(process.cwd(), "public", rel))) return null;
  // The static preview export is served from a sub-path, so public files are
  // referenced relatively there; normal builds use root-relative URLs.
  return process.env.ARTIFACT_EXPORT === "1" ? `./${rel}` : `/${rel}`;
}

export function getMedia(): Media {
  return Object.fromEntries(Object.entries(FILES).map(([k, rel]) => [k, publicUrl(rel)])) as Media;
}
