/**
 * PLACEHOLDER SERVICE REGION. Replace with the real three-digit ZIP prefixes
 * (or swap the lookup for an API call) once the region is set.
 */
export const SERVICE_ZIP_PREFIXES: readonly string[] = [
  "500", "501", "502", "503", "504", "505", "506", "507", "508", "509",
  "510", "511", "512", "513", "514", "515", "516",
];

export type CoverageStatus = "served" | "soon" | "invalid";

export function checkZip(raw: string): { status: CoverageStatus; zip: string } {
  const zip = raw.replace(/\D/g, "").slice(0, 5);
  if (zip.length !== 5) return { status: "invalid", zip };
  const served = SERVICE_ZIP_PREFIXES.some((prefix) => zip.startsWith(prefix));
  return { status: served ? "served" : "soon", zip };
}
