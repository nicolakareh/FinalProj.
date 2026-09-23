import { site } from "@/content/site";
import { Container } from "@/components/ui/Container";
import { Wordmark } from "@/components/ui/Wordmark";

export function Footer() {
  return (
    <footer className="border-t border-line">
      <Container className="flex flex-col gap-8 py-10 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-3">
          <Wordmark />
          <a href={`mailto:${site.email}`} className="text-sm text-ink-2 underline-offset-4 transition-colors duration-200 hover:text-ink hover:underline">
            {site.email}
          </a>
        </div>
        <nav aria-label="Footer">
          <ul className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
            {site.footer.links.map((link) => (
              <li key={link.href}>
                <a href={link.href} className="text-ink-2 transition-colors duration-200 hover:text-ink">
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <p className="text-xs text-ink-3">
          © {site.year} {site.name}. {site.complianceLine}
        </p>
      </Container>
    </footer>
  );
}
