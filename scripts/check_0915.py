import asyncio
from nepseman_api import NepseClient

async def main():
    async with NepseClient() as n:
        d = await n.price_history('NABIL')
        print('Looking for 2026-09-15...')
        for q in d:
            date_str = str(q.get('businessDate', ''))
            if '2026-09-15' in date_str:
                print('API raw row:')
                for k, v in q.items():
                    print(f'  {k}: {v}')
                break
        else:
            print('2026-09-15 not found in API data')

asyncio.run(main())