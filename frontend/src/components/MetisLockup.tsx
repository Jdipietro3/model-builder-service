/**
 * The full Metis lockup: the mark above the wordmark.
 *
 * Used where the logo stands alone and replaces the word "Metis" as text — the
 * expanded rail header and the two auth cards. Where the mark instead sits
 * beside live text (the home <h1>, the collapsed 56px rail), use <MetisMark>.
 *
 * The wordmark is traced from the supplied artwork rather than set in a
 * typeface, because the logo's face is not one this app ships. The trace walks
 * the boundary BETWEEN pixels of the 2000x2000 source and then simplifies with
 * Douglas-Peucker at 1.5 source px — about 0.05px at the size the rail renders
 * this, i.e. far below anything visible. M, E, T and I came out at exactly 16,
 * 12, 8 and 4 vertices: their true corner counts, so those four are exact
 * rather than approximated. Only S has real curvature, and it carries 74 of the
 * 114 total vertices.
 *
 * TWO colors, deliberately: the eye takes `currentColor` (so a caller tints it
 * with `text-accent`), while the wordmark takes --foreground. That mirrors the
 * supplied artwork, which pairs an amber eye with a wordmark in the opposite
 * value — dark on paper, light on this app's near-black ground. Binding the
 * wordmark to --foreground rather than a literal hex is the honest expression
 * of what it is: the product's name, set in the same value as every other piece
 * of text in the app.
 *
 * The iris is a knockout rather than a painted disc, because in the source
 * artwork it is transparent — the white you see in the logo on paper is the
 * page showing through. So the ground shows through the eye on any surface.
 *
 * Regenerate with `scratchpad/trace.py` if the artwork ever changes; do not
 * hand-edit the path data.
 */

import { MetisEye } from "@/components/MetisMark";

const MASK_ID = "metis-lockup-iris";

export default function MetisLockup({
  size = 40,
  className,
}: {
  /** Rendered height in px; width follows the lockup's 1.32:1 ratio. */
  size?: number;
  className?: string;
}) {
  return (
    <svg
      viewBox="137 252 1683 1279"
      width={(size * 1683) / 1279}
      height={size}
      className={className}
      fill="currentColor"
      // This one carries the brand name itself: it REPLACES the "Metis" text at
      // every site that uses it, so unlike <MetisMark> it must not be
      // aria-hidden or the rail header and both auth screens would announce no
      // name at all.
      role="img"
      aria-label="Metis"
      focusable="false"
    >
      <MetisEye maskId={MASK_ID} />
      <g fill="var(--foreground)">
        {/* M */}
        <path d="M215 1119 321 1119 404 1400 406 1400 408 1394 488 1120 594 1119 672 1522 574 1521 528 1246 525 1250 449 1522 361 1522 283 1245 235 1522 137 1522Z" />
        {/* E */}
        <path d="M711 1119 944 1119 944 1200 800 1200 800 1280 938 1280 938 1360 800 1360 800 1441 944 1442 944 1522 711 1522Z" />
        {/* T */}
        <path d="M983 1119 1302 1119 1302 1200 1187 1200 1187 1522 1098 1522 1098 1200 983 1200Z" />
        {/* I */}
        <path d="M1341 1119 1429 1119 1429 1522 1341 1522Z" />
        {/* S */}
        <path d="M1633 1113 1675 1114 1699 1118 1726 1126 1750 1138 1771 1154 1789 1176 1799 1197 1806 1227 1806 1242 1722 1242 1716 1219 1704 1201 1684 1190 1661 1186 1637 1186 1614 1192 1602 1199 1590 1214 1588 1235 1592 1244 1602 1254 1632 1267 1723 1289 1766 1307 1785 1320 1798 1333 1807 1346 1816 1367 1821 1400 1819 1427 1812 1451 1796 1478 1779 1495 1750 1513 1719 1524 1688 1530 1660 1532 1620 1530 1590 1524 1552 1509 1524 1489 1506 1469 1491 1440 1484 1412 1483 1389 1573 1389 1576 1410 1587 1431 1605 1447 1623 1455 1643 1459 1671 1459 1696 1453 1714 1443 1726 1428 1729 1417 1728 1403 1725 1395 1714 1383 1688 1370 1600 1347 1571 1337 1548 1326 1520 1304 1509 1289 1501 1272 1496 1248 1497 1215 1505 1188 1519 1165 1541 1144 1571 1127 1599 1118Z" />
      </g>
    </svg>
  );
}
