from database import db
from analysis import indicators as ind

rows = db.get_ohlc('NABIL', limit_days=100)
df = ind.to_dataframe(rows)

window = df.tail(14)
low14 = window['low'].min()
high14 = window['high'].max()
close = df['close'].iloc[-1]

print('Window dates (14):')
for d in window['date'].tolist():
    print(' ', d)
print()
print('low14 :', low14)
print('high14:', high14)
print('close :', close)

k_manual = 100 * (close - low14) / (high14 - low14)
print('Manual %K:', round(k_manual, 2))
print()

k_s, d_s = ind.stochastic(df)
print('Code %K:', round(float(k_s.iloc[-1]), 2))
print('Code %D:', round(float(d_s.iloc[-1]), 2))