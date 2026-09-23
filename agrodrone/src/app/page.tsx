import { Nav } from "@/components/sections/Nav";
import { Hero } from "@/components/sections/Hero";
import { ProofSlot } from "@/components/sections/ProofSlot";
import { Stats } from "@/components/sections/Stats";
import { FieldDemo } from "@/components/sections/FieldDemo";
import { HowItWorks } from "@/components/sections/HowItWorks";
import { Services } from "@/components/sections/Services";
import { Comparison } from "@/components/sections/Comparison";
import { Estimator } from "@/components/sections/Estimator";
import { Coverage } from "@/components/sections/Coverage";
import { FinalCta } from "@/components/sections/FinalCta";
import { Footer } from "@/components/sections/Footer";

export default function Home() {
  return (
    <>
      <Nav />
      <main id="main">
        <Hero />
        <ProofSlot />
        <Stats />
        <FieldDemo />
        <HowItWorks />
        <Services />
        <Comparison />
        <Estimator />
        <Coverage />
        <FinalCta />
      </main>
      <Footer />
    </>
  );
}
