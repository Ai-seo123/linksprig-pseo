import pandas as pd
import sys

excel_path = r"C:\Users\ARNAV\Downloads\LinkSprig-Blogs-Topics-Keywords-22ndMay'26.xlsx"
df = pd.read_excel(excel_path)
df.columns = [c.strip() for c in df.columns]

if "Topics" in df.columns:
    print("SUCCESS: Topics column found")
else:
    print("[ERROR] 'Topics' column not found in Excel sheet.")
    print(f"[INFO] Found columns: {', '.join(df.columns)}")
    sys.exit(1)
