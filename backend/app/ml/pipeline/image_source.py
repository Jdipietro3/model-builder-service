"""Image data source (scaffold).

Contract this will lock in when implemented:
- ``load`` resolves a file or folder (or a manifest CSV of paths + labels) into a
  manifest of image references — it does NOT read pixels eagerly.
- ``payload`` is a DataLoader-style object that yields decoded/transformed batches
  lazily, so training loops (see ``deep_learning.EpochTrainer``) iterate without
  holding the whole dataset in memory.
- The profile captures class balance, image count, and basic dimensions.
"""

from .base import LoadedData, ProgressCb, register_source


class ImageDataSource:
    data_shape = "image"

    def load(self, path: str, plan: dict, progress: ProgressCb) -> LoadedData:
        raise NotImplementedError("image data source not yet implemented")


register_source(ImageDataSource())
