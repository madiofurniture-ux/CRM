// Documents (quotes, invoices, PO lines) default to 0% — a pre-filled 18%
// silently taxed drafts that were never meant to carry GST. Mirrors
// models.GST_DOC_DEFAULT / GST_SLABS server-side.
export const GST_DEFAULT = 0;
export const GST_SLABS = [0, 5, 12, 18, 28];
