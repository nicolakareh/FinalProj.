import { Nav } from "@/components/sections/Nav";
import { Hero } from "@/components/sections/Hero";
import { ProofSlot } from "@/components/sections/ProofSlot";
import { Stats } from "@/components/sections/Stats";
import { FieldDemo } from "@/components/sections/FieldDemo";
import { HowItWorks } from "@/components/sections/HowItWorks";
import { Services } from "@/components/sections/Services";
import { Aircraft } from "@/components/sections/Aircraft";
import { Comparison } from "@/components/sections/Comparison";
import { Estimator } from "@/components/sections/Estimator";
import { Coverage } from "@/components/sections/Coverage";
import { FinalCta } from "@/components/sections/FinalCta";
import { Footer } from "@/components/sections/Footer";
import { getMedia } from "@/lib/media";

export default function Home() {
  const media = getMedia();
  return (
    <>
      <Nav />
      <main id="main">
        <Hero media={media} />
        <ProofSlot />
        <Stats />
        <FieldDemo />
        <HowItWorks />
        <Services
          images={{
            fertilizer: media.serviceFertilizer,
            protection: media.serviceProtection,
            seeding: media.serviceSeeding,
            mapping: media.serviceMapping,
          }}
        />
        <Aircraft media={media} />
        <Comparison />
        <Estimator />
        <Coverage />
        <FinalCta />
      </main>
      <Footer />
    </>
  );
}
