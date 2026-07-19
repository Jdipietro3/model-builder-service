"""Text data source (scaffold).

Contract this will lock in when implemented:
- The plan names the text column(s); ``load`` returns the raw strings plus a light
  profile (row count, length distribution, language guess, empty-row count).
- Embedding/vectorization is deliberately NOT done here: it is model-in-the-loop
  preprocessing owned by the task runner (a clustering runner and a classifier want
  different representations of the same text), so the payload stays raw text.
"""

from .base import LoadedData, ProgressCb, register_source


class TextDataSource:
    data_shape = "text"

    def load(self, path: str, plan: dict, progress: ProgressCb) -> LoadedData:
        raise NotImplementedError("text data source not yet implemented")


register_source(TextDataSource())
