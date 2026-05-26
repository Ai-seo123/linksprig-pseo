import os
import shutil
import subprocess
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from auth import verify_password, create_access_token, verify_captcha, get_current_user
from config import ADMIN_PASSWORD_HASH

app = FastAPI(title="LinkSprig API", version="1.0.0")

# Setup CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LoginRequest(BaseModel):
    password: str
    captchaToken: str

@app.post("/login")
def login(request: LoginRequest):
    # Verify Captcha
    if not verify_captcha(request.captchaToken):
        raise HTTPException(status_code=400, detail="Invalid CAPTCHA")
    
    # Verify Password
    if not verify_password(request.password, ADMIN_PASSWORD_HASH):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )
    
    # Generate JWT
    access_token = create_access_token(data={"sub": "admin"})
    return {"token": access_token}

# In-memory store for background job statuses
jobs_status = {}  # filename -> {"status": "queued" | "processing" | "completed" | "failed", "error": str | None}

def process_uploaded_file(file_path: str, filename: str):
    """Background task to run the appropriate script based on file type"""
    ext = filename.split('.')[-1].lower()
    script_to_run = None
    
    if ext == "html":
        script_to_run = "import_html_posts.py"
    elif ext == "csv":
        script_to_run = "push_csv_to_wp.py"
    elif ext in ["xls", "xlsx"]:
        script_to_run = "generate_blogs_from_excel.py"
        
    if not script_to_run:
        jobs_status[filename] = {"status": "failed", "error": f"Unsupported file extension: {ext}"}
        print(f"Unsupported file extension: {ext}")
        return

    # Update job state to processing
    jobs_status[filename] = {"status": "processing", "error": None}

    # Find where the script is located relative to main.py
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(backend_dir)
    script_path = os.path.join(parent_dir, script_to_run)
    
    if os.path.exists(script_path):
        env = os.environ.copy()
        env["UPLOADED_FILE_PATH"] = os.path.abspath(file_path)
        try:
            # Run using virtual environment's Python interpreter
            venv_python = os.path.join(parent_dir, ".venv", "Scripts", "python.exe")
            if not os.path.exists(venv_python):
                venv_python = "python"
                
            subprocess.run([venv_python, script_path], env=env, cwd=parent_dir, check=True)
            jobs_status[filename] = {"status": "completed", "error": None}
            print(f"Successfully processed {filename} with {script_to_run}")
        except subprocess.CalledProcessError as e:
            jobs_status[filename] = {"status": "failed", "error": f"Script failed with exit code {e.returncode}"}
            print(f"Error executing {script_to_run}: {e}")
        except Exception as e:
            jobs_status[filename] = {"status": "failed", "error": str(e)}
            print(f"Error executing {script_to_run}: {e}")
    else:
        jobs_status[filename] = {"status": "failed", "error": "Script missing on server"}
        print(f"Script missing at: {script_path}")


@app.post("/api/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), 
    username: str = Depends(get_current_user)
):
    valid_extensions = ["html", "csv", "xlsx", "xls"]
    ext = file.filename.split('.')[-1].lower()
    
    if ext not in valid_extensions:
        raise HTTPException(status_code=400, detail="Unsupported file format")

    # Save the file temporarily
    upload_dir = os.path.join("..", "output", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Set initial job status and dispatch background processing task
    jobs_status[file.filename] = {"status": "queued", "error": None}
    background_tasks.add_task(process_uploaded_file, file_path, file.filename)
    
    return {"message": "File uploaded and queued for processing", "filename": file.filename}

@app.get("/api/jobs")
def get_jobs_status(username: str = Depends(get_current_user)):
    return jobs_status

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

