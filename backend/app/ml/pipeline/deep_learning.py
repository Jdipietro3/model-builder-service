"""Epoch-based training loop contract for deep-learning task runners.

The tabular supervised path fits a model once (``estimator.fit(X, y)``). Image and
text runners can't work that way — they iterate a DataLoader-style payload over many
epochs on a chosen device. Rather than duplicate that loop in each runner, they will
subclass ``EpochTrainer`` and fill in the model, loss, and step logic while inheriting
the device selection + epoch/batch orchestration.

This is deliberately NOT registered as a ``TaskRunner``: it is shared machinery a
future image/text runner composes with, not a task family the dispatcher selects.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable

from .base import LoadedData

# Per-epoch callback: (epoch_index, metrics_dict) -> None. Lets a runner stream
# progress/metrics without EpochTrainer knowing how progress is reported.
EpochCb = Callable[[int, dict], None]


class EpochTrainer(ABC):
    """Abstract epoch/batch training loop over a DataLoader-style payload.

    Subclasses own the *what* (model, optimizer, loss, a single train/eval step);
    this base owns the *how* (pick a device, loop epochs, iterate batches, invoke the
    per-epoch callback). Concrete runners wrap an instance and expose it through the
    ``TaskRunner.run`` contract, returning a ``RunOutcome`` like any other family.
    """

    def __init__(self, epochs: int, batch_size: int, device: str | None = None) -> None:
        self.epochs = epochs
        self.batch_size = batch_size
        # None => auto-select (e.g. "cuda" if available else "cpu") in select_device.
        self.device = device

    @abstractmethod
    def select_device(self) -> str:
        """Resolve and return the compute device to train on."""
        raise NotImplementedError("select_device not yet implemented")

    @abstractmethod
    def build_model(self, data: LoadedData, spec: dict) -> Any:
        """Instantiate the model and move it to the selected device."""
        raise NotImplementedError("build_model not yet implemented")

    @abstractmethod
    def train_step(self, model: Any, batch: Any) -> dict:
        """Run one optimization step on a batch; return metrics for aggregation."""
        raise NotImplementedError("train_step not yet implemented")

    @abstractmethod
    def evaluate(self, model: Any, data: LoadedData) -> dict:
        """Evaluate the trained model; return the metrics for the results envelope."""
        raise NotImplementedError("evaluate not yet implemented")

    def fit(self, data: LoadedData, spec: dict, on_epoch: EpochCb) -> Any:
        """Drive the epoch loop. Concrete implementation lands with the first DL runner."""
        raise NotImplementedError("epoch training loop not yet implemented")
