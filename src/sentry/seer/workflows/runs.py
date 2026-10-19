from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from functools import partial
from typing import Any, Literal
from uuid import UUID

from django.db import router, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from pydantic import BaseModel

from sentry.seer.agent.client import SeerAgentClient
from sentry.seer.agent.types import FeatureRunStatus
from sentry.seer.models.run import SeerAgentRun, SeerRun, SeerRunMirrorStatus
from sentry.seer.models.workflow import (
    SeerWorkflowConfig,
    SeerWorkflowRun,
    SeerWorkflowRunExecution,
    SeerWorkflowRunStatus,
    SeerWorkflowStrategy,
)
from sentry.seer.workflows.schemas import (
    WorkflowResult,
    WorkflowResultError,
    WorkflowRunError,
    WorkflowRunExtras,
    WorkflowRunSnapshot,
)
from sentry.seer.workflows.workflow import SeerWorkflow
from sentry.utils import json

logger = logging.getLogger(__name__)
TERMINAL_STATUSES = {"complete", "partial", "failed"}


def get_or_create_workflow_run(
    *,
    organization_id: int,
    workflow_config_id: int,
    request_key: str,
    inputs: BaseModel,
) -> tuple[SeerWorkflowRun, bool]:
    """Accept an invocation once; retries keep its original configuration and inputs."""
    if not request_key or len(request_key) > 256:
        raise ValueError("Request keys must contain between 1 and 256 characters")

    using = router.db_for_write(SeerWorkflowRun)
    runs = SeerWorkflowRun.objects.using(using).filter(
        organization_id=organization_id,
        config_id_at_creation=workflow_config_id,
        request_key=request_key,
    )
    existing = runs.first()
    if existing is not None:
        return existing, False

    with transaction.atomic(using):
        config = (
            SeerWorkflowConfig.objects.select_for_update()
            .filter(id=workflow_config_id, organization_id=organization_id)
            .first()
        )
        # Recheck after the lock, including when a concurrent delete cleared the config FK.
        existing = runs.first()
        if existing is not None:
            return existing, False
        if config is None:
            raise SeerWorkflowConfig.DoesNotExist

        snapshot = WorkflowRunSnapshot(
            config_version=config.version,
            strategy=SeerWorkflowStrategy(config.strategy),
            filters=config.filters,
            project_ids=tuple(SeerWorkflow(config).get_project_ids()),
            output_policy=config.output_policy,
            inputs=json.loads(inputs.json()),
        )
        run = SeerWorkflowRun.objects.using(using).create(
            organization_id=organization_id,
            workflow_config=config,
            config_id_at_creation=config.id,
            request_key=request_key,
            status=SeerWorkflowRunStatus.RUNNING,
            date_started=timezone.now(),
            snapshot=json.loads(snapshot.json()),
        )
    return run, True


def complete_workflow_run(
    *,
    organization_id: int,
    workflow_run_id: int,
    result: Literal["complete", "partial"] | WorkflowRunError = "complete",
) -> SeerWorkflowRun:
    """Record the terminal result of an accepted invocation, including no-work success."""
    with transaction.atomic(router.db_for_write(SeerWorkflowRun)):
        run = SeerWorkflowRun.objects.select_for_update().get(
            id=workflow_run_id, organization_id=organization_id, request_key__isnull=False
        )
        if run.date_completed is not None:
            return run

        if isinstance(result, WorkflowRunError):
            run.status = SeerWorkflowRunStatus.FAILED
            run.error = result.dict()
        else:
            run.status = result
            run.error = None
        run.date_completed = timezone.now()
        run.save(update_fields=["status", "error", "date_completed", "date_updated"])
    return run


def get_workflow_runs(
    *, organization_id: int, workflow_config_id: int | None = None
) -> QuerySet[SeerWorkflowRun]:
    runs = SeerWorkflowRun.objects.filter(organization_id=organization_id)
    if workflow_config_id is not None:
        runs = runs.filter(
            Q(config_id_at_creation=workflow_config_id) | Q(workflow_config_id=workflow_config_id)
        )
    return runs.order_by("-date_added", "-id")


def create_workflow_run(
    client: SeerAgentClient,
    *,
    strategy: SeerWorkflowStrategy,
    feature_id: str,
    payload: dict[str, Any],
    title: str,
    extras: Mapping[str, Any] | None = None,
) -> SeerWorkflowRun:
    """Atomically create a workflow with one execution and enqueue its dispatch."""
    run = client.start_feature_run(
        feature_id=feature_id,
        payload=payload,
        title=title,
        flush=False,
        extras={**(extras or {}), "status": "running", "error": None},
        referrer=feature_id,
        on_run_created=partial(_create_workflow_run, strategy=strategy),
    )
    return run.workflow_execution.run


def _create_workflow_run(seer_run: SeerRun, *, strategy: SeerWorkflowStrategy) -> None:
    config = SeerWorkflowConfig.get_or_create_for_strategy(seer_run.organization_id, strategy)
    run = SeerWorkflowRun.objects.create(
        organization_id=seer_run.organization_id, workflow_config=config
    )
    SeerWorkflowRunExecution.objects.create(run=run, seer_run=seer_run)


def deliver_workflow_result(
    *,
    feature_id: str,
    organization_id: int,
    run_uuid: UUID,
    status: FeatureRunStatus,
    result: dict[str, Any] | None,
    error: str | None,
    parse_result: Callable[[dict[str, Any], SeerAgentRun], WorkflowResult],
) -> None:
    log_extra = {
        "feature_id": feature_id,
        "organization_id": organization_id,
        "run_uuid": str(run_uuid),
        "status": status,
    }
    logger.info("seer.workflow.delivery.received", extra=log_extra)
    agent_run = (
        SeerAgentRun.objects.select_related("run__organization")
        .filter(run__organization_id=organization_id, source=feature_id, run__uuid=run_uuid)
        .first()
    )
    if agent_run is None:
        logger.warning("seer.workflow.delivery.missing_run", extra=log_extra)
        return
    if agent_run.extras.get("status") in TERMINAL_STATUSES:
        logger.info("seer.workflow.delivery.already_finished", extra=log_extra)
        return
    finish = partial(
        finish_workflow_run,
        agent_run.run_id,
        organization_id=organization_id,
        feature_id=feature_id,
    )
    if status != "completed" or result is None:
        logger.warning("seer.workflow.delivery.failed", extra={**log_extra, "error": error})
        finish(error="Seer could not complete this workflow.")
        return
    try:
        parsed = parse_result(result, agent_run)
    except WorkflowResultError as exc:
        logger.exception("seer.workflow.result_processing_failed", extra=log_extra)
        finish(error=str(exc))
        return
    except Exception:
        logger.exception("seer.workflow.invalid_output", extra=log_extra)
        finish(error="Seer returned results that could not be loaded.")
        return
    finish(result=parsed)


def finish_workflow_run(
    run_id: int,
    *,
    organization_id: int,
    feature_id: str,
    result: WorkflowResult | None = None,
    error: str | None = None,
) -> None:
    """Finalize the single-execution workflow created by create_workflow_run."""
    with transaction.atomic(router.db_for_write(SeerAgentRun)):
        agent_run = (
            SeerAgentRun.objects.select_for_update(of=("self",))
            .filter(run_id=run_id, run__organization_id=organization_id, source=feature_id)
            .first()
        )
        if agent_run is None or agent_run.extras.get("status") in TERMINAL_STATUSES:
            return
        extras: WorkflowRunExtras = {
            "status": "failed" if error else result.status if result else "complete",
            "error": error,
        }
        agent_run.update(extras={**agent_run.extras, **(result.extras if result else {}), **extras})
        SeerWorkflowRun.objects.filter(
            organization_id=organization_id,
            executions__seer_run_id=run_id,
            date_completed__isnull=True,
        ).update(date_completed=timezone.now())
    logger.info(
        "seer.workflow.run.finished",
        extra={
            "feature_id": feature_id,
            "run_id": run_id,
            "organization_id": organization_id,
            "status": extras["status"],
            "error": error,
        },
    )


def get_workflow_run_status(agent_run: SeerAgentRun) -> WorkflowRunExtras:
    extras: WorkflowRunExtras = agent_run.extras
    if (
        extras["status"] not in TERMINAL_STATUSES
        and agent_run.run.mirror_status == SeerRunMirrorStatus.FAILED
    ):
        return {
            "status": "failed",
            "error": "Seer could not start this workflow.",
        }
    return {
        "status": extras["status"],
        "error": extras["error"],
    }
