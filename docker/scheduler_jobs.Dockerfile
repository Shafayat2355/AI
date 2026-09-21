# Image that runs scheduler.jobs.* -- what Airflow's DockerOperator actually
# executes (see scheduler/airflow/dag_common.py) for every DAG task.
#
# Installs this repo's requirements/training.txt (superset of base.txt: adds
# scikit-learn/pandas/numpy/feast/pyarrow, per Phase 11/12) -- feature
# generation, training, and evaluation jobs (scheduler/jobs/feature_generation_job.py,
# nightly_training_job.py, model_evaluation_job.py) need these; every other
# job in this image only needs what training.txt already re-exports from
# base.txt, so one requirements file for the whole image keeps this Dockerfile
# simple rather than splitting jobs across two images.
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
COPY requirements/training.txt requirements/training.txt
RUN pip install --no-cache-dir -r requirements/training.txt

COPY . .

ENTRYPOINT ["python", "-m", "scheduler.jobs.cli"]
