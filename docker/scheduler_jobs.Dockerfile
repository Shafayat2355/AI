# Image that runs scheduler.jobs.* -- what Airflow's DockerOperator actually
# executes (see scheduler/airflow/dag_common.py) for every DAG task.
#
# Installs this repo's OWN requirements/base.txt (sqlalchemy, pydantic, fastapi,
# redis, aiokafka, ...) -- this image is exactly what every other app service
# would run in, NOT the Airflow image. Deliberately self-contained rather than
# extending docker/base.Dockerfile, which is still an unimplemented Phase 2
# stub as of this phase.
FROM python:3.12-slim AS runtime

# postgresql-client provides pg_dump for scheduler/jobs/database_backup_job.py.
# redis-tools is not required -- cache access goes through cache/redis_client.py
# (the redis-py client, already in requirements/base.txt), never the redis-cli
# binary.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements/base.txt requirements/base.txt
RUN pip install --no-cache-dir -r requirements/base.txt

COPY . .

ENTRYPOINT ["python", "-m", "scheduler.jobs.cli"]
