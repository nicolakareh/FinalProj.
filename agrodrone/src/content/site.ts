/**
 * All site copy lives here. Edit text freely; components only read from this
 * file and never hard-code words. Anything marked PLACEHOLDER is waiting on a
 * real figure, asset, or decision.
 */
import type { ApplicationId, CropId } from "@/lib/estimator";

export type NavLink = { label: string; href: string };

export const site = {
  name: "AgroDrone",
  /** PLACEHOLDER: replace with the real contact address. */
  email: "hello@agrodrone.co",
  year: 2026,
  /** Keep licensing language neutral until the real credentials are confirmed. */
  complianceLine: "FAA-compliant operations.",

  nav: {
    links: [
      { label: "Service", href: "#services" },
      { label: "How it works", href: "#how-it-works" },
      { label: "Coverage", href: "#coverage" },
    ] satisfies NavLink[],
    cta: { label: "Get a quote", href: "#quote" },
  },

  hero: {
    headline: "Precision spraying from the air.",
    subline:
      "Fertilizer, crop protection and seeding by drone: mapped to the row, done in hours, nothing on the ground.",
    primary: { label: "Get a quote", href: "#quote" },
    secondary: { label: "See how it works", href: "#how-it-works" },
    /** PLACEHOLDER trust items. Edit or remove once the real claims are confirmed. */
    trust: ["Licensed operators", "Every acre mapped", "No soil compaction"],
    /**
     * Set to "/media/hero.mp4" once the clip exists in public/media.
     * Intended shot: a spray drone crossing a crop field at golden hour, low
     * angle, slow lateral tracking, 8 to 12 seconds, seamless loop, no audio.
     */
    video: null as string | null,
    videoPoster: null as string | null,
  },

  /** Empty, labeled slot where partner or press logos will go. No fake logos. */
  proof: {
    enabled: true,
    label: "Reserved for partner and press logos",
    slots: 5,
  },

  stats: {
    eyebrow: "The problem",
    headline: "Ground rigs were built for a different field.",
    lead: "Three numbers that explain why growers are looking up.",
    /**
     * PLACEHOLDER VALUES. Replace "XX" with sourced figures and cite each one
     * in `source`. Nothing here is a real statistic yet.
     */
    items: [
      {
        value: "XX",
        suffix: "%",
        label: "of spray windows lost to wet or inaccessible ground",
        source: "",
      },
      {
        value: "XX",
        suffix: "%",
        label: "yield lost in wheel-tracked rows to compaction",
        source: "",
      },
      {
        value: "XX",
        suffix: "%",
        label: "of inputs over-applied by blanket ground spraying",
        source: "",
      },
    ],
  },

  demo: {
    eyebrow: "Live demo",
    headline: "Watch a field get covered.",
    lead: "Pick an application, set the field size, and see the flight plan the drone would fly.",
    modes: [
      { id: "fertilizer", label: "Fertilizer", color: "#3f6b3a" },
      { id: "pesticide", label: "Pesticide", color: "#4f6f8f" },
      { id: "seeding", label: "Seeding", color: "#b5892f" },
    ] as const,
    sizeLabel: "Field size",
    panel: {
      title: "Flight plan",
      application: "Application",
      field: "Field",
      passes: "Passes",
      pass: "Current pass",
      swath: "Swath",
      time: "Est. time on field",
      coverage: "Covered",
      elapsed: "elapsed",
    },
    status: {
      ready: "Ready",
      flying: "In flight",
      paused: "Paused",
      done: "Complete",
    },
    controls: {
      play: "Fly the field",
      pause: "Pause",
      resume: "Resume",
      replay: "Fly again",
    },
  },

  how: {
    eyebrow: "How it works",
    headline: "Four steps. One afternoon.",
    lead: "From the first survey pass to the as-applied report, every job follows the same plan.",
    scrollHint: "Scroll",
    steps: [
      {
        title: "Map the field",
        body: "A survey pass builds a precise map of boundaries, obstacles and rows.",
      },
      {
        title: "Plan the flight",
        body: "Software plans route, swath and rate. You approve it from your phone.",
      },
      {
        title: "Spray",
        body: "The drone flies the plan low and level, row by row, at an even droplet size.",
      },
      {
        title: "Report",
        body: "You get an as-applied map: what went where, at what rate, and when.",
      },
    ],
  },

  services: {
    eyebrow: "Service",
    headline: "One aircraft. Four jobs.",
    lead: "Every application runs on the same mapped, approved flight plan.",
    tabs: [
      {
        id: "fertilizer",
        label: "Fertilizer",
        title: "Fertilizer",
        body: "Granular or foliar, applied at variable rate by zone.",
        bullets: [
          "Variable rate from your prescription map",
          "Granular or liquid, same aircraft",
          "Flown inside the weather window, not after it",
        ],
        /** Intended shot: granular spread over young corn, drone low in frame, dawn light. */
        media: "Fertilizer application over young corn",
      },
      {
        id: "protection",
        label: "Crop protection",
        title: "Crop protection",
        body: "Fungicide and insecticide passes, targeted to the rows that need them.",
        bullets: [
          "Low altitude, low drift",
          "Spot or full-field treatment",
          "No wheel damage in standing crop",
        ],
        /** Intended shot: fine spray over a mature canopy, side light showing the droplet curtain. */
        media: "Fungicide pass over a mature canopy",
      },
      {
        id: "seeding",
        label: "Seeding",
        title: "Seeding",
        body: "Cover crops broadcast into standing crop, weeks before harvest.",
        bullets: [
          "Even density across the field",
          "Into standing corn or beans",
          "A whole field in a day",
        ],
        /** Intended shot: seed broadcast into tall standing corn, top-down, late summer. */
        media: "Cover-crop seeding into standing corn",
      },
      {
        id: "mapping",
        label: "Field mapping",
        title: "Field mapping",
        body: "A survey flight before any application, and a record after it.",
        bullets: [
          "Boundaries, obstacles and rows",
          "Plant-health imagery by row",
          "As-applied records for every pass",
        ],
        /** Intended shot: tablet held over a field showing the as-applied map, field behind it. */
        media: "As-applied map on a tablet in the field",
      },
    ],
  },

  comparison: {
    eyebrow: "Drone vs. tractor",
    headline: "Same job. Different footprint.",
    lead: "Qualitative for now. Figures will be added once they are sourced.",
    columns: { criterion: "Criterion", drone: "Drone", tractor: "Tractor" },
    rows: [
      {
        criterion: "Speed",
        drone: "Sets up in minutes and flies the plan without stopping.",
        tractor: "Limited by ground speed, turning and refills.",
      },
      {
        criterion: "Soil compaction",
        drone: "None. Nothing touches the ground.",
        tractor: "Wheel tracks on every pass.",
      },
      {
        criterion: "Wet or steep fields",
        drone: "Flies over standing water and slopes.",
        tractor: "Waits for the ground to dry.",
      },
      {
        criterion: "Chemical use",
        drone: "Targeted swaths and rates by zone.",
        tractor: "Blanket application across the field.",
      },
      {
        criterion: "Labor",
        drone: "One licensed pilot and one truck.",
        tractor: "Operator, rig, fuel and maintenance.",
      },
    ],
  },

  estimator: {
    eyebrow: "Estimator",
    headline: "How long would your field take?",
    lead: "A rough estimate from field size, crop and application. Exact pricing comes after we map your field.",
    acresLabel: "Field size (acres)",
    cropLabel: "Crop",
    applicationLabel: "Application",
    crops: [
      { id: "corn", label: "Corn" },
      { id: "soybeans", label: "Soybeans" },
      { id: "wheat", label: "Wheat" },
      { id: "orchard", label: "Orchard or vineyard" },
      { id: "pasture", label: "Pasture" },
      { id: "other", label: "Other" },
    ] satisfies { id: CropId; label: string }[],
    applications: [
      { id: "fertilizer", label: "Fertilizer" },
      { id: "protection", label: "Crop protection" },
      { id: "seeding", label: "Seeding" },
    ] satisfies { id: ApplicationId; label: string }[],
    resultLabel: "Estimated time on field",
    resultBadge: "Estimate",
    disclaimer: "Estimate only. Final timing depends on terrain, obstacles and weather.",
    cta: "Request exact pricing",
  },

  coverage: {
    eyebrow: "Coverage",
    headline: "Where we fly.",
    lead: "We are building out region by region. Check whether your farm is inside the current service area.",
    /** PLACEHOLDER: name the real region once it is set. */
    mapLabel: "Service region · placeholder",
    inputLabel: "ZIP code",
    inputPlaceholder: "50010",
    button: "Check",
    results: {
      served: "Yes. We fly in {zip}. Request a quote and we will map your field.",
      soon: "Not yet. {zip} is outside the current area, but we are expanding. Leave your details and we will tell you when we get there.",
      invalid: "Enter a five-digit ZIP code.",
    },
  },

  cta: {
    headline: "Ready for your next application?",
    lead: "Tell us about the field. We will come back with a flight plan and a firm price.",
    fields: {
      name: "Your name",
      farm: "Farm name",
      acres: "Acres",
      email: "Email",
      phone: "Phone",
    },
    submit: "Request a quote",
    privacy: "We only use this to reply about your field.",
    success: {
      title: "Got it, {name}.",
      body: "We will be in touch within one business day with next steps.",
    },
    errors: {
      name: "Please add your name.",
      acres: "Enter the number of acres.",
      email: "Enter a valid email address.",
      phone: "Enter a valid phone number, or leave it blank.",
    },
  },

  footer: {
    links: [
      { label: "Service", href: "#services" },
      { label: "How it works", href: "#how-it-works" },
      { label: "Coverage", href: "#coverage" },
    ] satisfies NavLink[],
  },
} as const;

export type Site = typeof site;
export type DemoModeId = Site["demo"]["modes"][number]["id"];
