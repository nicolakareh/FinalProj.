import Image from "next/image";
import { MediaPlaceholder } from "./MediaPlaceholder";

type Props = {
  src: string | null;
  alt: string;
  /** Corner label shown on the placeholder when no file is in place. */
  label: string;
  className?: string;
  sizes?: string;
  priority?: boolean;
  tone?: "light" | "dark";
};

/** An image when the file exists, a labeled placeholder when it does not. */
export function MediaImage({ src, alt, label, className, sizes = "100vw", priority, tone = "light" }: Props) {
  if (!src) return <MediaPlaceholder label={label} className={className} tone={tone} />;
  return (
    <div className={className}>
      <Image src={src} alt={alt} fill sizes={sizes} priority={priority} className="object-cover" />
    </div>
  );
}
