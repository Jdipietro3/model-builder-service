/**
 * The Metis mark: an asterisk set inside an open eye.
 *
 * Geometry is transcribed from the supplied logo artwork, measured off the
 * 2000x2000 source at `METIS_LOGO_TEXT.png` and kept in that file's own
 * coordinate space — hence the `viewBox` starting at 254 252 rather than 0 0.
 * Working in source coordinates means every number below is something that was
 * measured rather than something that was derived, so there is no arithmetic
 * here to get wrong or to drift out of step with the artwork:
 *
 *   lens      x 254..1718, y 252..1040   (center 986,646)
 *   iris      circle r 288 at 986,648
 *   asterisk  3 bars, 428 long x 93 wide, at 0/60/120 degrees
 *
 * The lens is a QUADRATIC curve, not a circular-arc lens. That was checked
 * rather than assumed: fitting a true circular lens (R=877 from the sagitta)
 * misses the measured edge by up to 24px on the flanks, while the quadratic
 * below tracks it within 2.2px everywhere across the full 788px height. The
 * control points are 2*apex - endpoint, which is what puts a quadratic's apex
 * on the measured 252 and 1040.
 *
 * Everything paints in `currentColor`, so a caller sets the color with an
 * ordinary text utility — `text-accent` in the rail, `text-zinc-100` on the
 * auth screens — instead of this component owning a hue.
 *
 * The iris is a KNOCKOUT, not a white disc. In the source artwork it is
 * transparent — the white you see in the logo on paper is the page showing
 * through — so cutting it here is faithful rather than a shortcut, and it means
 * the mark needs exactly one color to render correctly on any background.
 * The asterisk is then painted back inside that hole.
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
const MASK_ID = "metis-mark-iris";

/** The eye, the iris hole, and the asterisk — shared with <MetisLockup>. */
export function MetisEye({ maskId }: { maskId: string }) {
  return (
    <>
      <mask id={maskId}>
        {/* White keeps, black cuts. Lens kept, iris cut back out of it, then
            the asterisk restored inside that hole. */}
        <path d="M254 646 Q986 -142 1718 646 Q986 1434 254 646 Z" fill="white" />
        <circle cx="986" cy="648" r="288" fill="black" />
        <g fill="white">
          <rect x="940" y="432" width="93" height="428" />
          <rect x="940" y="432" width="93" height="428" transform="rotate(60 986 646)" />
          <rect x="940" y="432" width="93" height="428" transform="rotate(120 986 646)" />
        </g>
      </mask>
      <rect
        x="254"
        y="252"
        width="1464"
        height="788"
        fill="currentColor"
        mask={`url(#${maskId})`}
      />
    </>
  );
}

export default function MetisMark({
  size = 20,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      viewBox="254 252 1464 788"
      width={(size * 1464) / 788}
      height={size}
      className={className}
      // Decorative wherever it appears: every placement of the bare mark pairs
      // it with the word "Metis" in text, so announcing it again would just be
      // noise. <MetisLockup> is the one that carries its own name, because it
      // replaces that text rather than sitting beside it.
      aria-hidden="true"
      focusable="false"
    >
      <MetisEye maskId={MASK_ID} />
    </svg>
  );
}
