import os

from rq import Worker
from rq.worker import SimpleWorker

from job_queue import job_queue, redis_conn

# RQ's default Worker isolates each job in a forked child process (POSIX
# only). Windows has no os.fork(), so dev falls back to SimpleWorker, which
# runs jobs in-process instead. Production (Linux) uses the real Worker.
worker_cls = Worker if hasattr(os, "fork") else SimpleWorker

if __name__ == "__main__":
    worker_cls([job_queue], connection=redis_conn).work()
