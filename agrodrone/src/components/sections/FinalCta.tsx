"use client";

import { useEffect, useId, useState, type FormEvent } from "react";
import { site } from "@/content/site";
import { cn } from "@/lib/cn";
import { Container } from "@/components/ui/Container";
import { Button } from "@/components/ui/Button";
import { Reveal } from "@/components/ui/Reveal";
import { PREFILL_EVENT } from "./Estimator";

type Values = { name: string; farm: string; acres: string; email: string; phone: string };
type Errors = Partial<Record<keyof Values, string>>;

const EMPTY: Values = { name: "", farm: "", acres: "", email: "", phone: "" };

function validate(v: Values): Errors {
  const e: Errors = {};
  const { errors } = site.cta;
  if (!v.name.trim()) e.name = errors.name;
  if (!(Number(v.acres) > 0)) e.acres = errors.acres;
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.email.trim())) e.email = errors.email;
  if (v.phone.trim() && v.phone.replace(/\D/g, "").length < 10) e.phone = errors.phone;
  return e;
}

const inputClass =
  "h-12 w-full rounded-xl border bg-paper/5 px-4 text-base text-paper outline-none transition-[border-color,box-shadow] duration-200 placeholder:text-paper/35 hover:border-paper/40 focus:border-paper/70 focus:ring-4 focus:ring-paper/10";

/**
 * Quote request. Client-side validation and a success state only.
 * TODO: wire `submit` to a backend (form endpoint, email API, or CRM). For now
 * the submission is logged to the console.
 */
export function FinalCta() {
  const { cta } = site;
  const [values, setValues] = useState<Values>(EMPTY);
  const [errors, setErrors] = useState<Errors>({});
  const [submitted, setSubmitted] = useState<Values | null>(null);
  const id = useId();

  useEffect(() => {
    function onPrefill(e: Event) {
      const detail = (e as CustomEvent<{ acres?: number }>).detail;
      if (detail?.acres) setValues((v) => ({ ...v, acres: String(detail.acres) }));
    }
    window.addEventListener(PREFILL_EVENT, onPrefill);
    return () => window.removeEventListener(PREFILL_EVENT, onPrefill);
  }, []);

  function update<K extends keyof Values>(key: K, value: string) {
    setValues((v) => ({ ...v, [key]: value }));
    if (errors[key]) setErrors((e) => ({ ...e, [key]: undefined }));
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const next = validate(values);
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    // TODO: replace with a real request once the backend exists.
    console.log("[AgroDrone] quote request", { ...values, submittedAt: new Date().toISOString() });
    setSubmitted(values);
  }

  const fields: Array<{ key: keyof Values; type: string; autoComplete: string; inputMode?: "numeric" | "email" | "tel"; span?: boolean }> = [
    { key: "name", type: "text", autoComplete: "name" },
    { key: "farm", type: "text", autoComplete: "organization" },
    { key: "acres", type: "number", autoComplete: "off", inputMode: "numeric" },
    { key: "email", type: "email", autoComplete: "email", inputMode: "email" },
    { key: "phone", type: "tel", autoComplete: "tel", inputMode: "tel", span: true },
  ];

  return (
    <section id="quote" className="section-pad scroll-mt-16 bg-ink text-paper">
      <Container>
        <div className="grid gap-12 lg:grid-cols-[1.1fr_1fr] lg:gap-20">
          <Reveal>
            <h2 className="type-h2 max-w-[14ch]">{cta.headline}</h2>
            <p className="type-lead mt-6 max-w-[40ch] text-paper/70">{cta.lead}</p>
            <a href={`mailto:${site.email}`} className="mt-10 inline-block text-[15px] text-paper/70 underline-offset-4 transition-colors duration-200 hover:text-paper hover:underline">
              {site.email}
            </a>
          </Reveal>

          <Reveal delay={0.12} amount={0.2}>
          {submitted ? (
            <div role="status" className="flex flex-col justify-center rounded-3xl border border-paper/15 p-8">
              <p className="type-h3 text-2xl sm:text-3xl">{cta.success.title.replace("{name}", submitted.name.trim().split(" ")[0])}</p>
              <p className="mt-4 max-w-[36ch] text-paper/70">{cta.success.body}</p>
            </div>
          ) : (
            <form onSubmit={submit} noValidate className="grid gap-5 sm:grid-cols-2">
              {fields.map((f) => {
                const fieldId = `${id}-${f.key}`;
                const error = errors[f.key];
                return (
                  <div key={f.key} className={cn(f.span && "sm:col-span-2")}>
                    <label htmlFor={fieldId} className="type-eyebrow text-paper/60">
                      {cta.fields[f.key]}
                    </label>
                    <input
                      id={fieldId}
                      name={f.key}
                      type={f.type}
                      inputMode={f.inputMode}
                      autoComplete={f.autoComplete}
                      value={values[f.key]}
                      onChange={(e) => update(f.key, e.target.value)}
                      aria-invalid={error ? true : undefined}
                      aria-describedby={error ? `${fieldId}-error` : undefined}
                      className={cn(inputClass, "mt-2", error ? "border-paper/70" : "border-paper/15")}
                    />
                    {error && (
                      <p id={`${fieldId}-error`} className="mt-2 text-sm text-paper/70">
                        {error}
                      </p>
                    )}
                  </div>
                );
              })}
              <div className="flex flex-col gap-4 sm:col-span-2 sm:flex-row sm:items-center sm:justify-between">
                <Button type="submit" variant="inverse" size="lg" arrow>
                  {cta.submit}
                </Button>
                <p className="text-sm text-paper/50">{cta.privacy}</p>
              </div>
            </form>
          )}
          </Reveal>
        </div>
      </Container>
    </section>
  );
}
