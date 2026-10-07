import os

from dotenv import load_dotenv
from redis import Redis
from rq import Queue

load_dotenv()

redis_conn = Redis.from_url(os.environ["REDIS_URL"])
job_queue = Queue(connection=redis_conn)
