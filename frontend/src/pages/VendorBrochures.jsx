import Catalogues from "@/pages/Catalogues";

/** Vendors' own brochures and price lists: kept for landing-price holders,
 * never shared outside, imported into the Virtual Catalogue (Catalogues in
 * vendor mode; docs/VENDOR_CATALOGUES.md). */
export default function VendorBrochures() {
  return <Catalogues vendorMode />;
}
