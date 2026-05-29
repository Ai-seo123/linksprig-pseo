import subprocess
import os

env = os.environ.copy()
env["UPLOADED_FILE_PATH"] = r"C:\Users\ARNAV\Downloads\LinkSprig-Blogs-Topics-Keywords-22ndMay'26.xlsx"

try:
    result = subprocess.run(
        [r".\.venv\Scripts\python.exe", "generate_blogs_from_excel.py"], 
        env=env, 
        cwd=r"C:\Users\ARNAV\.gemini\antigravity\scratch\linksprig-pseo", 
        capture_output=True,
        text=True,
        check=True
    )
    print("SUCCESS")
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
except subprocess.CalledProcessError as e:
    print("FAILED WITH CODE", e.returncode)
    print("STDOUT:", repr(e.stdout))
    print("STDERR:", repr(e.stderr))
    error_details = (e.stderr or e.stdout or "").strip()
    if not error_details:
        error_details = f"script failed with exit code {e.returncode}"
    print("ERROR DETAILS:", error_details)
