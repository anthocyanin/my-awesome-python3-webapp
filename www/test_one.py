from www.orm import create_pool
from www.models import User, Blog, Comment
import asyncio


async def test_db(loop):
    await create_pool(loop=loop, user='www-data', password='www-data', db='awesome')
    u = User(name='Test', email='test@example.com', passwd='1234567890', image='about:blank')
    await u.save()

loop = asyncio.get_event_loop()
loop.run_until_complete(test_db(loop))
loop.run_forever()

for x in test_db(loop):
    pass

