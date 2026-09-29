import sqlite3
import pandas as pd
from config import DATABASE_PATH
conn = sqlite3.connect(DATABASE_PATH)
df = pd.read_sql("SELECT * FROM _vbi_source_registry", conn)
print("Registry:\n", df)
conn.close()
