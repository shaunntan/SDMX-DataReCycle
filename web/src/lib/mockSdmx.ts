import type { ReviewItem, SuggestedChange } from "./types";

/** STUB: stands in for the (not yet built) AI metadata review. */
export function mockAiReview(
  artifactType: string,
  artifactId: string,
  items: ReviewItem[],
): SuggestedChange[] {
  const pick = (n: number) => items[n % Math.max(items.length, 1)];
  const canned: Array<[string, string]> = [
    ["Name is not in sentence case; SDMX name conventions prefer sentence case.", " (revised)"],
    ["Description is missing a trailing full stop.", "."],
    ["Value appears abbreviated; expanded for clarity.", " — expanded"],
  ];
  const out: SuggestedChange[] = [];
  for (let i = 0; i < Math.min(3, items.length); i++) {
    const it = pick(i * 3 + 1);
    const base = (it.status === "edited" ? it.edited_value : it.suggested_value) ?? "";
    const [rationale, suffix] = canned[i % canned.length];
    out.push({
      change_id: `ai-${artifactId}-${i + 1}`,
      artifact_type: artifactType as SuggestedChange["artifact_type"],
      artifact_id: artifactId,
      item_id: it.item_id,
      field: it.field,
      current_value: base,
      suggested_value: `${base}${suffix}`,
      rationale,
    });
  }
  return out;
}
