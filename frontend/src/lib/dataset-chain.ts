import { Dataset } from "@/lib/api";

/** A dataset is a chain tip if no other dataset's parent_dataset_id points at it. */
export function isChainTip(d: Dataset, all: Dataset[]): boolean {
  return !all.some((x) => x.parent_dataset_id === d.id);
}

/** Walk parent_dataset_id links forward from `datasetId` to the newest version
 * in its chain (used to detect "a newer version exists" for the retrain CTA). */
export function findChainTip(datasetId: string, all: Dataset[]): Dataset | undefined {
  let current = all.find((d) => d.id === datasetId);
  if (!current) return undefined;
  for (;;) {
    const next: Dataset | undefined = all.find((d) => d.parent_dataset_id === current!.id);
    if (!next) return current;
    current = next;
  }
}
