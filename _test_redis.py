import asyncio
import os

from dotenv import load_dotenv
from redis.asyncio import Redis

load_dotenv()


async def main():
    redis = Redis.from_url(os.environ["REDIS_URL"])
    await redis.set("test_key", "hello")
    value = await redis.get("test_key")
    print("Value from Redis:", value)
    await redis.aclose()


asyncio.run(main())
