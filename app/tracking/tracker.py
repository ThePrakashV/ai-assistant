import logging
import os
import threading
import warnings

import httpx

from app.core.config import settings
from app.orchestrator.models import TaskRecord

# MLflow import pannum bodhu varra harmless pydantic warning + "View run" console noise mute
os.environ.setdefault("MLFLOW_LOGGING_LEVEL", "WARNING")
warnings.filterwarnings("ignore", message=".*protected namespace.*")


class Tracker:
    """MLflow la runs ah log pannum. Server illana / error na assistant ah thadukkaadhu."""

    def __init__(self, experiment: str | None = None) -> None:
        self.enabled = False
        self._client = None
        self._experiment_id: str | None = None
        self._error_shown = False
        self.experiment = experiment or settings.mlflow_experiment
        uri = settings.mlflow_tracking_uri

        if not settings.mlflow_enabled:
            return

        # Server run aagudha nu modhalil check (illana 'tracking off' nu sollitu poidrom)
        try:
            httpx.get(f"{uri}/health", timeout=1.5).raise_for_status()
        except Exception:
            print(f"[MLflow] Server kidaikkala ({uri}). Tracking OFF. 'docker compose up -d' run pannu.")
            return

        try:
            from mlflow.tracking import MlflowClient  # lazy import (startup slow aagaama irukka)

            logging.getLogger("mlflow").setLevel(logging.WARNING)  # import apparam thirumba mute

            client = MlflowClient(tracking_uri=uri)
            existing = client.get_experiment_by_name(self.experiment)
            self._experiment_id = (
                existing.experiment_id if existing else client.create_experiment(self.experiment)
            )
            self._client = client
        except Exception as exc:
            print(f"[MLflow] Tracking OFF ({type(exc).__name__}: {exc})")
            return

        self.enabled = True
        print(f"[MLflow] Tracking ON -> {uri} (experiment: {self.experiment})")

    # ---------- Generic: oru run log pannum ----------
    def log_run(
        self,
        run_name: str,
        params: dict | None = None,
        metrics: dict | None = None,
        tags: dict | None = None,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> None:
        if not self.enabled:
            return

        from mlflow.entities import Metric, Param, RunTag  # noqa: PLC0415

        run = self._client.create_run(
            self._experiment_id, start_time=start_ms, tags=tags or {}, run_name=run_name
        )
        run_id = run.info.run_id
        stamp = end_ms or start_ms or 0

        self._client.log_batch(
            run_id,
            metrics=[Metric(key, float(value), stamp, 0) for key, value in (metrics or {}).items()],
            params=[Param(key, str(value)[:500]) for key, value in (params or {}).items()],
            tags=[RunTag(key, str(value)) for key, value in (tags or {}).items()],
        )
        self._client.set_terminated(run_id, status="FINISHED", end_time=end_ms)

    # ---------- Task: oru user request ----------
    def log_task(self, task: TaskRecord) -> None:
        """Background thread la log pannum, so user reply slow aagaadhu."""
        if not self.enabled:
            return
        snapshot = task.model_copy(deep=True)
        threading.Thread(target=self._log_task_safe, args=(snapshot,), daemon=True).start()

    def _log_task_safe(self, task: TaskRecord) -> None:
        try:
            self._log_task(task)
        except Exception as exc:
            if not self._error_shown:  # error thirumba thirumba print aagaama, oru dhadavai mattum
                print(f"[MLflow] log error: {type(exc).__name__}: {exc}")
                self._error_shown = True

    def _log_task(self, task: TaskRecord) -> None:
        ended = task.ended or task.created
        steps_done = sum(1 for step in task.steps if step.status == "done")
        steps_failed = sum(1 for step in task.steps if step.status == "failed")

        metrics = {
            "total_ms": (ended - task.created) * 1000,
            "plan_ms": task.plan_ms,
            "n_steps": len(task.steps),
            "steps_done": steps_done,
            "steps_failed": steps_failed,
            "retries": sum(step.retries for step in task.steps),
            "success": 1.0 if task.status == "done" else 0.0,
        }
        for step in task.steps:
            if step.started and step.ended:
                metrics[f"step_{step.index}_ms"] = (step.ended - step.started) * 1000

        params = {
            "task_id": task.id,
            "source": task.source,
            "routes": ",".join(step.route or "?" for step in task.steps),
            "llm_model": settings.ollama_model,
            "intent_threshold": settings.intent_threshold,
            "max_parallel_steps": settings.max_parallel_steps,
        }
        if settings.mlflow_log_text:
            params["text"] = task.text[:250]

        self.log_run(
            run_name=f"task-{task.id}",
            params=params,
            metrics=metrics,
            tags={"status": task.status, "source": task.source},
            start_ms=int(task.created * 1000),
            end_ms=int(ended * 1000),
        )