import asyncio
from nepseman_api import NepseClient

async def main():
    async with NepseClient() as n:
        d = await n.price_history('NABIL')
        print('API rows:', len(d))
        print('Last 20 dates:')
        for q in d[:20]:
            print(' ', q.get('businessDate'), 'close:', q.get('closePrice'))

asyncio.run(main())