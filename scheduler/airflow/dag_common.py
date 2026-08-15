"""Shared configuration every DAG in ``scheduler/airflow/dags/`` builds on: a
common ``default_args`` dict, :func:`build_job_task` (the one place a DAG
constructs a task that runs one ``scheduler.jobs`` module), and
:func:`on_job_failure` (the on-failure callback wired onto every task).

Every task built here runs via ``DockerOperator`` against
``PLATFORM_JOBS_IMAGE`` (built from ``docker/scheduler_jobs.Dockerfile``) --
**not** by importing ``scheduler.jobs`` into Airflow's own Python process.
This is deliberate and load-bearing, not a style preference: installing this
platform's own dependencies (``sqlalchemy>=2``, ``pydantic>=2``, ``fastapi``)
into the same environment as ``apache-airflow==2.10.4`` was tried while
building this phase and breaks immediately -- Airflow's own pinned
constraints force ``sqlalchemy`` down to 1.4.x and a ``typing_extensions``
incompatible with ``pydantic`` v2, which crashes ``pydantic``/``fastapi``
imports outright. See ``docs/PHASE10_WORKFLOW_ORCHESTRATION.md`` Sec 3 for the
exact reproduction. Every task therefore runs the platform's own code inside
the platform's own image/dependency set, with Airflow only ever orchestrating
*when* and *whether* it runs -- never importing it directly.

Configuration reaches each task via ``env_file`` pointing at this repo's own
``.env`` (the same file every other service already reads through
``config.settings.get_settings()``) -- not a second, Airflow-specific copy of
connection strings/settings maintained in DAG code.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from airflow import DAG
from airflow.models import Variable
from airflow.providers.docker.operators.docker import DockerOperator

_logger = logging.getLogger("airflow.task")


class _PlatformDockerOperator(DockerOperator):
    """``DockerOperator`` with ``env_file`` excluded from Jinja templating.

    ``DockerOperator.template_ext`` includes ``".env"`` -- Airflow's generic
    template-*file* resolution machinery (``BaseOperator.resolve_template_files``)
    therefore tries to open whatever path ``env_file`` holds and replace the
    field's value with that file's *rendered contents*, not just validate the
    path. Confirmed while building this phase: parsing a DAG using
    ``env_file`` with ``DagBag`` raises ``jinja2.exceptions.TemplateNotFound``
    before the mounted path exists, and even once it does exist this would
    replace the intended host *path* string with the file's raw *contents* --
    the opposite of what ``docker run --env-file <path>`` needs. Excluding
    ``env_file`` here keeps every other templated field (``command``,
    ``environment``, ...) working exactly as ``DockerOperator`` already
    provides.
    """

    template_fields = tuple(f for f in DockerOperator.template_fields if f != "env_file")


#: Built from docker/scheduler_jobs.Dockerfile -- see that file and
#: docs/PHASE10_WORKFLOW_ORCHESTRATION.md Sec 4 "Docker Compose integration"
#: for the exact build/tag step this name assumes has already run.
PLATFORM_JOBS_IMAGE = "trading-platform-scheduler-jobs:latest"

#: Matches the network docker-compose creates for this project by default
#: (``<project-directory-name>_default``) -- overridden via the
#: ``AIRFLOW_DOCKER_NETWORK`` Airflow Variable if a deployment names it
#: differently (docker-compose's ``-p``/``COMPOSE_PROJECT_NAME``, or a
#: non-Compose orchestrator entirely).
_DEFAULT_DOCKER_NETWORK = "ai_default"

#: Airflow Variable holding this repo's path *as the Docker host sees it* --
#: DockerOperator talks to the host's Docker daemon (via the mounted
#: ``docker.sock``, the standard "Docker-outside-of-Docker" pattern used here
#: so a task container is a sibling of, not nested inside, the Airflow
#: container) to start each task's container, so any path passed to that
#: daemon -- including ``env_file`` below -- must be valid from the *host's*
#: filesystem, not the Airflow container's. A hardcoded in-container path
#: would be silently wrong: the host daemon would look for it on the host and
#: either fail (nothing there) or, worse, resolve to some unrelated real path.
#: docker-compose.yml sets this Variable's underlying env var
#: (``AIRFLOW_VAR_HOST_REPO_PATH``) from its own ``${PWD}`` at container
#: start -- the standard, portable way for a container to learn the host path
#: it was bind-mounted from.
_HOST_REPO_PATH_VARIABLE = "host_repo_path"

DEFAULT_ARGS: dict[str, Any] = {
    "owner": "trading-platform",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
    "execution_timeout": timedelta(hours=1),
}


def on_job_failure(context: dict[str, Any]) -> None:
    """Airflow ``on_failure_callback``: logs a structured line via Airflow's
    own task logger.

    This -- not a Slack/PagerDuty webhook -- is today's real alert channel for
    a DAG failure: Airflow's own UI already shows a failed task/DAG run in
    red, and a deployment's Airflow install typically already has its own
    email/Slack-on-failure configuration at the ``airflow.cfg``/environment
    level (orthogonal to this codebase, and not duplicated here). Routing a
    DAG failure through this platform's own ``alerts/`` module instead is a
    natural enhancement once that module has a real implementation (still a
    Phase 2 stub as of this phase) -- see ``scheduler/jobs/alert_sweep_job.py``'s
    docstring for the identical reasoning applied to the alert-sweep job
    itself.
    """
    task_instance = context["task_instance"]
    _logger.error(
        "airflow_task_failed dag_id=%s task_id=%s run_id=%s",
        task_instance.dag_id,
        task_instance.task_id,
        context.get("run_id"),
    )


def _resolve_env_file_path() -> str:
    """``{host_repo_path Variable}/.env``, degrading to an obviously-wrong
    placeholder if the Variable is not set (e.g. before ``airflow-init`` has
    run) rather than raising.

    Confirmed while building this phase: calling ``Variable.get`` without a
    default and having it raise ``KeyError`` breaks *every* DAG in this
    package at once (``DagBag`` parsing aborts the whole module on the first
    unhandled exception) -- an unrelated, temporarily-unseeded Variable should
    never take down every scheduled job. A task that actually runs with this
    placeholder fails obviously and immediately (the path does not exist),
    which is the correct, visible failure mode -- as opposed to either
    breaking DAG parsing entirely or silently resolving to some unrelated
    real path.
    """
    host_repo_path = Variable.get(_HOST_REPO_PATH_VARIABLE, default_var=None)
    if not host_repo_path:
        _logger.error(
            "airflow_variable_not_set variable=%s -- env_file will be a "
            "placeholder path until this Variable is seeded (see airflow-init "
            "in docker-compose.yml)",
            _HOST_REPO_PATH_VARIABLE,
        )
        return "/UNSET_HOST_REPO_PATH_VARIABLE/.env"
    return f"{host_repo_path}/.env"


def build_job_task(
    *,
    dag: DAG,
    task_id: str,
    job_module_name: str,
    docker_network: str = _DEFAULT_DOCKER_NETWORK,
    env_file_path: str | None = None,
    **operator_kwargs: Any,
) -> DockerOperator:
    """Build one task that runs ``python -m scheduler.jobs.cli
    <job_module_name>`` inside :data:`PLATFORM_JOBS_IMAGE`.

    The single place every DAG in this package builds a task, so the
    image/network/env-file convention lives in exactly one spot rather than
    being repeated (and potentially drifting) across eleven DAG files.

    ``env_file_path`` defaults to ``None``, meaning: resolve
    ``{Variable.get("host_repo_path")}/.env`` directly in Python at call time
    -- not via a Jinja template string, since ``env_file`` is deliberately
    excluded from ``_PlatformDockerOperator.template_fields`` (see that
    class's docstring), so a ``{{ ... }}`` expression in its value would
    never actually be rendered. Calling ``Variable.get`` here means the
    Variable must exist whenever Airflow parses this DAG file (every
    ``dag_dir_list_interval`` cycle, not just when a task runs) -- standard,
    common practice for an Airflow Variable, and satisfied by seeding it once
    via ``airflow-init`` (see docker-compose.yml).
    """
    resolved_env_file = env_file_path if env_file_path is not None else _resolve_env_file_path()
    return _PlatformDockerOperator(
        task_id=task_id,
        image=PLATFORM_JOBS_IMAGE,
        command=["python", "-m", "scheduler.jobs.cli", job_module_name],
        docker_url="unix://var/run/docker.sock",
        network_mode=docker_network,
        env_file=resolved_env_file,
        auto_remove="success",
        mount_tmp_dir=False,
        on_failure_callback=on_job_failure,
        dag=dag,
        **operator_kwargs,
    )


__all__ = ["DEFAULT_ARGS", "PLATFORM_JOBS_IMAGE", "build_job_task", "on_job_failure"]
