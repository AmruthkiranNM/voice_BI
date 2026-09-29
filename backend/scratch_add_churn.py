import sqlite3
import pandas as pd
from config import DATABASE_PATH
conn = sqlite3.connect(DATABASE_PATH)
df = pd.DataFrame({
    'geography': ['France', 'Spain', 'Germany'],
    'gender': ['Female', 'Male', 'Female'],
    'numofproducts': [1, 2, 1],
    'hascrcard': [1, 0, 1],
    'isactivemember': [1, 1, 0],
    'exited': [0, 0, 1],
    'm1': [100.5, 200.5, 300.5],
    'm2': [100.5, 200.5, 300.5],
    'm3': [100.5, 200.5, 300.5],
    'm4': [100.5, 200.5, 300.5]
})
df = pd.concat([df] * 4000, ignore_index=True) # 12000 rows
# modify m1, m2, m3, m4 slightly so they are unique enough to be measures
import numpy as np
df['m1'] = df['m1'] + np.random.randn(12000)
df['m2'] = df['m2'] + np.random.randn(12000)
df['m3'] = df['m3'] + np.random.randn(12000)
df['m4'] = df['m4'] + np.random.randn(12000)
df.to_sql('Churn_Modelling', conn, if_exists='replace', index=False)
conn.close()
print("Added Churn_Modelling with 12000 rows and 4 measures.")
