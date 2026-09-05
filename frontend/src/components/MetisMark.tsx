/**
 * The Metis mark: an asterisk above an open eye.
 *
 * The in-app twin of `app/icon.svg`. Two differences from that file, both
 * deliberate: this one paints no background (it sits on whatever surface it is
 * dropped onto) and it strokes in `currentColor`, so a caller sets the color
 * with an ordinary text utility — `text-accent` in the rail, `text-zinc-100` on
 * the auth screens — instead of this component owning a hardcoded hue.
 *
 * The iris is punched out with a `<mask>` rather than by overpainting a
 * background-colored circle, because there is no known background here to
 * overpaint with. Everything inside the mask is greyscale on purpose: white
 * keeps, black cuts.
 *
 * Not a server/client boundary concern — it renders no state and no handlers,
 * so it stays a plain server component and can be imported from either side.
 */

/**
 * A constant, not a generated id.
 *
 * `useId()` would force this into a client component, and `Math.random()` would
 * produce a different id on the server than on the client and trip a hydration
 * mismatch the moment a "use client" file imports this (Sidebar does). Neither
 * is needed: every instance of this mark stamps out byte-identical mask
 * geometry, so all of them referencing one shared definition is not a collision
 * — it is the correct result.
 */
const MASK_ID = "metis-iris";

export default function MetisMark({
  size = 20,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      className={className}
      fill="none"
      // Decorative wherever it appears: every placement pairs it with the
      // word "Metis" in text, so announcing it again would just be noise.
      aria-hidden="true"
      focusable="false"
    >
      <g stroke="currentColor" strokeWidth="4.2" strokeLinecap="round">
        <line x1="32" y1="9" x2="32" y2="27" />
        <line x1="24.2" y1="13.5" x2="39.8" y2="22.5" />
        <line x1="24.2" y1="22.5" x2="39.8" y2="13.5" />
      </g>

      <mask id={MASK_ID}>
        {/* White keeps the almond, black cuts the iris back out of it, white
            restores the pupil inside that hole. */}
        <path d="M6 44 Q32 22 58 44 Q32 66 6 44 Z" fill="white" />
        <circle cx="32" cy="44" r="10.5" fill="black" />
        <circle cx="32" cy="44" r="5.4" fill="white" />
      </mask>

      <rect width="64" height="64" fill="currentColor" mask={`url(#${MASK_ID})`} />
    </svg>
  );
}
