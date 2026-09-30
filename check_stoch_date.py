from database import db
from analysis import indicators as ind

TARGET_DATE = "2026-09-28"

rows = db.get_ohlc('NABIL', limit_days=100)
df = ind.to_dataframe(rows)

# Cut the DataFrame to end at TARGET_DATE
df = df[df['date'] <= TARGET_DATE].reset_index(drop=True)

k, d = ind.stochastic(df)
print(f'Stochastic for {TARGET_DATE}:')
print(f'  %K = {round(float(k.iloc[-1]), 2)}')
print(f'  %D = {round(float(d.iloc[-1]), 2)}')

# Show the 14-bar window used
print()
print('Last 14 bars used:')
for _, r in df.tail(14).iterrows():
    print(f"  {r['date']}  H={r['high']}  L={r['low']}  C={r['close']}")