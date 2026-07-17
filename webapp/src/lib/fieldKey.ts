// Mirrors docstill.schema.field_key_from_name / KEY_PATTERN.

export const FIELD_KEY_RE = /^[a-z][a-z0-9_]{0,63}$/

/** Derive a snake_case machine key from a display label. ASCII-folds accents;
 * labels with no usable ASCII (e.g. CJK) come back empty and the user must
 * type a key manually. */
export function fieldKeyFromName(name: string): string {
  const folded = name
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^\x20-\x7e]/g, '')
  let slug = folded
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
  slug = slug.slice(0, 64).replace(/_+$/, '')
  if (slug && !/^[a-z]/.test(slug)) slug = `f_${slug}`.slice(0, 64).replace(/_+$/, '')
  return slug
}
