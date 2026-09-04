import { type ReactNode, useState } from "react";

import { useCityPhoto } from "../hooks/useCityPhoto";
import { useI18n } from "../i18n";

interface Props {
  /** City to photograph. Falls back to a plain panel when there is none. */
  city: string;
  children: ReactNode;
}

/**
 * A photograph of the destination, with content laid over it.
 *
 * The image is decoration, never information: the panel is fully legible
 * without it, and it only fades in once the file has actually decoded, so a
 * slow connection shows a clean coloured panel rather than a half-painted
 * photo behind white text.
 *
 * The scrim is not optional. Wikipedia's lead images are photographs taken by
 * whoever took them — bright skies, pale buildings, high-contrast water — and
 * white text over an unknown photograph is unreadable often enough that the
 * gradient has to assume the worst.
 */
export function HeroPhoto({ city, children }: Props) {
  const { t } = useI18n();
  const photo = useCityPhoto(city);
  const [loaded, setLoaded] = useState(false);

  return (
    <section className="relative overflow-hidden rounded-2xl bg-accent">
      {photo && (
        <img
          src={photo}
          alt=""
          aria-hidden
          loading="lazy"
          decoding="async"
          onLoad={() => setLoaded(true)}
          className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-700 ${
            loaded ? "opacity-100" : "opacity-0"
          }`}
        />
      )}

      {/* Darkened towards the start edge, where the text sits, and left
          clearer on the far side so the photograph is still visible. */}
      <div
        aria-hidden
        className="absolute inset-0"
        style={{
          background:
            "linear-gradient(to var(--scrim-direction, right), " +
            "rgb(4 20 24 / 0.82) 0%, rgb(4 20 24 / 0.58) 45%, rgb(4 20 24 / 0.25) 100%)",
        }}
      />

      <div className="relative p-6 sm:p-10">{children}</div>

      {photo && loaded && (
        <p className="relative px-6 sm:px-10 pb-3 text-[10px] text-white/55">
          {t("hero.photoCredit")}
        </p>
      )}
    </section>
  );
}
