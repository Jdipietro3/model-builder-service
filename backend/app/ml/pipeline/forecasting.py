"""Forecasting task runner (scaffold).

Contract this will lock in when implemented:
- Consumes a ``timeseries`` payload (time-ordered rows).
- Split is time-ordered with NO shuffling: train on the past, evaluate on the most
  recent tail. Evaluation is a backtest (rolling-origin) reporting MAPE / MASE.
- ``RunOutcome.results`` carries the common spine plus a ``horizon`` block (the
  forecast values + intervals over the requested future window) and a ``backtest``
  block; ``artifact`` is the fitted forecaster.
"""

from .base import LoadedData, ProgressCb, RunOutcome, register_runner


class ForecastingRunner:
    task_family = "forecasting"
    compatible_shapes = ("timeseries",)

    def run(self, data: LoadedData, spec: dict, plan: dict, progress: ProgressCb) -> RunOutcome:
        raise NotImplementedError("forecasting runner not yet implemented")


register_runner(ForecastingRunner())
