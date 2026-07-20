/**
 * Finalized-invoice line vs catalog price compare (pure helpers).
 * Desktop: InvoiceEditViewModel.ComparePricesToDatabaseAsync.
 */

/**
 * Compare one line's unit cents to catalog base price cents.
 * @param {number|string|null|undefined} unitPriceCents
 * @param {number|string|null|undefined} catalogPriceCents
 */
export function compareLineToCatalog(unitPriceCents, catalogPriceCents) {
  const unit = Number(unitPriceCents) || 0;
  const catalog = Number(catalogPriceCents) || 0;
  return {
    unit_price_cents: unit,
    catalog_price_cents: catalog,
    has_mismatch: unit !== catalog,
  };
}

/**
 * Flag invoice items against a partId → base_price_cents map.
 * Lines without part_id are left without mismatch flags.
 *
 * @param {Array<{ part_id?: number|null, unit_price_cents?: number }>} items
 * @param {Map<number, number>|Record<string, number>} catalogByPartId
 * @returns {Array<object>}
 */
export function flagPriceMismatches(items, catalogByPartId) {
  const lookup =
    catalogByPartId instanceof Map
      ? catalogByPartId
      : new Map(
          Object.entries(catalogByPartId || {}).map(([k, v]) => [Number(k), Number(v)])
        );

  return (items || []).map((it) => {
    const partId = it.part_id;
    if (partId == null) {
      return {
        ...it,
        has_price_mismatch: false,
        catalog_price_cents: null,
      };
    }
    const key = Number(partId);
    if (!lookup.has(key)) {
      return {
        ...it,
        has_price_mismatch: false,
        catalog_price_cents: null,
      };
    }
    const cmp = compareLineToCatalog(it.unit_price_cents, lookup.get(key));
    return {
      ...it,
      has_price_mismatch: cmp.has_mismatch,
      catalog_price_cents: cmp.has_mismatch ? cmp.catalog_price_cents : null,
    };
  });
}

export default {
  compareLineToCatalog,
  flagPriceMismatches,
};
