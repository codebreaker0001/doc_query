import os

from dotenv import load_dotenv
from redis.asyncio import Redis

load_dotenv()

redis_client = Redis.from_url(os.environ["REDIS_URL"])
