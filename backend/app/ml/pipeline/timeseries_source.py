"""Timeseries data source (scaffold).

Contract this will lock in when implemented:
- The plan must name a timestamp column; ``load`` parses it and returns rows in
  ascending time order (no shuffling anywhere downstream — order is signal).
- Frequency is inferred from the timestamp spacing (e.g. hourly/daily/weekly) and
  recorded in the profile so runners can pick horizons and resample sensibly.
- ``payload`` is a time-indexed DataFrame; gaps are surfaced in the profile rather
  than silently filled.
"""

from .base import LoadedData, ProgressCb, register_source


class TimeseriesDataSource:
    data_shape = "timeseries"

    def load(self, path: str, plan: dict, progress: ProgressCb) -> LoadedData:
        raise NotImplementedError("timeseries data source not yet implemented")


register_source(TimeseriesDataSource())
