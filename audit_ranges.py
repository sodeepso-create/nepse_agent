from database import db

rows = db.get_ohlc('NABIL', limit_days=250)
ranges = [(r['date'], round(r['high'] - r['low'], 2)) for r in rows]

# Median range as baseline
sorted_ranges = sorted(r for _, r in ranges)
med = sorted_ranges[len(sorted_ranges) // 2]
print(f'Median daily range: {med}')

print('\nRows with range > 3x median:')
suspects = [(d, r) for d, r in ranges if r > 3 * med]
for d, r in suspects:
    print(f'  {d}: range = {r}  ({r/med:.1f}x median)')
print(f'\nTotal suspect rows: {len(suspects)} / {len(ranges)}')
