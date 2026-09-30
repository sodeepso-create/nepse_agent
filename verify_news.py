from database import db

news = db.get_recent_news(limit=50)
if not news:
    print("No news in DB. Run: python main.py collect")
    raise SystemExit

print(f"Reviewing {len(news)} most recent classified items.\n")
print(f"{'DIR':<8} {'W':<2} {'CATEGORIES':<40} HEADLINE")
print("-" * 120)

for n in news:
    direction = (n.get("direction") or "?")[:7]
    weight = n.get("impact_weight") or 0
    cats = n.get("categories") or "[]"
    if isinstance(cats, str):
        cats = cats.replace('"', "").replace("[", "").replace("]", "")
    headline = (n.get("headline") or "")[:70]
    print(f"{direction:<8} {weight:<2} {cats[:40]:<40} {headline}")