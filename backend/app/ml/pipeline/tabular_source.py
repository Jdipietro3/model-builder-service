"""Tabular data source: CSV on disk -> profiled pandas DataFrame.

Wraps the existing tabular profiling helpers so the loading/profiling step is
owned by the pipeline layer rather than baked into the training executor.
"""

from ..profiling import load_csv, profile_dataframe
from .base import LoadedData, ProgressCb, register_source


class TabularDataSource:
    data_shape = "tabular"

    def load(self, path: str, plan: dict, progress: ProgressCb) -> LoadedData:
        # Same progress beat the monolithic run_plan emitted before touching data.
        progress("preparing", 10, "Loading and preparing data")
        df = load_csv(path)
        profile = profile_dataframe(df)
        return LoadedData(data_shape="tabular", profile=profile, payload=df)


# Register the instance (not the class — an earlier version registered the class
# and every lookup got an unbound type instead of a usable source).
register_source(TabularDataSource())
