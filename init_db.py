import sqlite3

print("Connecting to database...")
conn = sqlite3.connect('nepse.db')

print("Reading schema.sql...")
with open('database/schema.sql', 'r', encoding='utf-8') as f:
    schema_sql = f.read()

print("Creating tables...")
conn.executescript(schema_sql)
conn.commit()
conn.close()

print("Success! All tables have been created.")