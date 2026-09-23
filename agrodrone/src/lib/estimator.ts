/**
 * ---------------------------------------------------------------------------
 * PLACEHOLDER RATE CONSTANTS. Set these before launch.
 * Every number in this block is a stand-in so the estimator has something to
 * compute. None of them is a measured or quoted figure.
 * ---------------------------------------------------------------------------
 */
export const BASE_ACRES_PER_HOUR = 40; // PLACEHOLDER: flat, open field, one aircraft
export const SETUP_MINUTES = 20; // PLACEHOLDER: staging, mixing and pre-flight per job

export type CropId = "corn" | "soybeans" | "wheat" | "orchard" | "pasture" | "other";
export type ApplicationId = "fertilizer" | "protection" | "seeding";

/** PLACEHOLDER: relative speed by crop (1 = base rate). */
export const CROP_FACTORS: Record<CropId, number> = {
  corn: 1,
  soybeans: 1,
  wheat: 1.05,
  orchard: 0.7,
  pasture: 1.1,
  other: 1,
};

/** PLACEHOLDER: relative speed by application type (1 = base rate). */
export const APPLICATION_FACTORS: Record<ApplicationId, number> = {
  fertilizer: 1,
  protection: 1,
  seeding: 0.85,
};

/** Estimated minutes on field, including setup. Returns 0 for invalid input. */
export function estimateMinutes(acres: number, crop: CropId, application: ApplicationId): number {
  if (!Number.isFinite(acres) || acres <= 0) return 0;
  const rate = BASE_ACRES_PER_HOUR * CROP_FACTORS[crop] * APPLICATION_FACTORS[application];
  return Math.round(SETUP_MINUTES + (acres / rate) * 60);
}

/** "2 h 15 min", "45 min", or "0 min". */
export function formatMinutes(total: number): string {
  const minutes = Math.max(0, Math.round(total));
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m} min`;
  if (m === 0) return `${h} h`;
  return `${h} h ${m} min`;
}
