/** Default parameter values for a catalog step spec. @param {any} spec */
export function defaultParams(spec) {
  /** @type {Record<string, any>} */
  const out = {};
  for (const p of spec.params) if (p.default !== undefined && p.default !== null) out[p.name] = p.default;
  return out;
}
