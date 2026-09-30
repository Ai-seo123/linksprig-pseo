import os
import sys
import shutil
import subprocess
import json
import re
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, BackgroundTasks

# Add parent directory to path so db_helper can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db_helper
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

try:
    from .auth import verify_password, create_access_token, verify_captcha, get_current_user
    from .config import ADMIN_PASSWORD_HASH
    from .topic_generator import generate_topics
except ImportError:
    from auth import verify_password, create_access_token, verify_captcha, get_current_user
    from config import ADMIN_PASSWORD_HASH
    from topic_generator import generate_topics


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

class GenerateTopicsRequest(BaseModel):
    prompt: str

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

@app.post("/api/generate-topics")
def api_generate_topics(request: GenerateTopicsRequest, username: str = Depends(get_current_user)):
    try:
        topics = generate_topics(request.prompt)
        return {"topics": topics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
def startup_event():
    db_helper.clean_stale_jobs()

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
    elif ext == "json":
        script_to_run = "generate_blogs_from_json.py"
        
    if not script_to_run:
        db_helper.update_job_status(filename, "failed", f"Unsupported file extension: {ext}")
        print(f"Unsupported file extension: {ext}")
        return

    # Update job state to processing
    db_helper.update_job_status(filename, "processing")

    # Find where the script is located relative to main.py
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(backend_dir)
    script_path = os.path.join(parent_dir, script_to_run)
    
    if os.path.exists(script_path):
        env = os.environ.copy()
        env["UPLOADED_FILE_PATH"] = os.path.abspath(file_path)
        env["PYTHONWARNINGS"] = "ignore"
        try:
            # Run using virtual environment's Python interpreter
            venv_python = os.path.join(parent_dir, ".venv", "Scripts", "python.exe")
            if not os.path.exists(venv_python):
                venv_python = "python"
                
            result = subprocess.run(
                [venv_python, script_path], 
                env=env, 
                cwd=parent_dir, 
                capture_output=True,
                text=True,
                check=True
            )
            db_helper.update_job_status(filename, "completed")
            print(f"Successfully processed {filename} with {script_to_run}")
        except subprocess.CalledProcessError as e:
            err_output = (e.stderr or "").strip()
            out_output = (e.stdout or "").strip()

            # Search stdout and stderr for actionable error messages
            meaningful_lines = []
            for line in (out_output + "\n" + err_output).splitlines():
                line_s = line.strip()
                if any(tag in line_s for tag in ["[Error]", "[WARNING]", "WordPress Post Upload status:", "Details:", "Unauthorized", "Forbidden", "Bad Request", "RuntimeError:"]):
                    # Clean out Python traceback prefix if present
                    clean_line = re.sub(r'^[a-zA-Z0-9_.]*RuntimeError:\s*', '', line_s)
                    meaningful_lines.append(clean_line)

            if meaningful_lines:
                error_details = meaningful_lines[-1]
            elif err_output:
                tb_lines = [l.strip() for l in err_output.splitlines() if l.strip()]
                error_details = tb_lines[-1] if tb_lines else err_output
            else:
                error_details = out_output if out_output else f"Script failed with exit code {e.returncode}"

            if len(error_details) > 400:
                error_details = "..." + error_details[-397:]

            db_helper.update_job_status(filename, "failed", error_details)
            print(f"Error executing {script_to_run}: {error_details}")
            if e.stderr:
                print(f"Stderr:\n{e.stderr}")
            if e.stdout:
                print(f"Stdout:\n{e.stdout}")
        except Exception as e:
            db_helper.update_job_status(filename, "failed", str(e))
            print(f"Error executing {script_to_run}: {e}")
    else:
        db_helper.update_job_status(filename, "failed", "Script missing on server")
        print(f"Script missing at: {script_path}")


def run_migration_task(job_id: str):
    """Background task to run the migration script"""
    db_helper.update_job_status(job_id, "processing")

    # Find where the script is located relative to main.py
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(backend_dir)
    script_path = os.path.join(parent_dir, "migrate_existing_posts_images.py")
    
    if os.path.exists(script_path):
        env = os.environ.copy()
        env["PYTHONWARNINGS"] = "ignore"
        try:
            # Run using virtual environment's Python interpreter
            venv_python = os.path.join(parent_dir, ".venv", "Scripts", "python.exe")
            if not os.path.exists(venv_python):
                venv_python = "python"
                
            result = subprocess.run(
                [venv_python, script_path], 
                env=env, 
                cwd=parent_dir, 
                capture_output=True,
                text=True,
                check=True
            )
            db_helper.update_job_status(job_id, "completed")
            print(f"Successfully ran migration script")
        except subprocess.CalledProcessError as e:
            err_output = (e.stderr or "").strip()
            out_output = (e.stdout or "").strip()
            error_details = err_output if err_output else out_output
            
            if not error_details:
                error_details = f"Script failed with exit code {e.returncode}"
            else:
                if len(error_details) > 400:
                    error_details = "..." + error_details[-397:]
            db_helper.update_job_status(job_id, "failed", error_details)
            print(f"Error executing migration script: {e}")
            if e.stderr:
                print(f"Stderr:\n{e.stderr}")
        except Exception as e:
            db_helper.update_job_status(job_id, "failed", str(e))
            print(f"Error executing migration script: {e}")
    else:
        db_helper.update_job_status(job_id, "failed", "Migration script missing on server")
        print(f"Migration script missing at: {script_path}")


@app.post("/api/migrate")
async def trigger_migration(
    background_tasks: BackgroundTasks,
    username: str = Depends(get_current_user)
):
    job_id = "migrate_existing_posts_images.py"
    
    # Check if there is an active job running for migration
    existing_job = db_helper.get_job_status(job_id)
    if existing_job and existing_job.get("status") in ["queued", "processing"]:
        raise HTTPException(
            status_code=400,
            detail="A migration job is already running. Please wait until it completes."
        )
        
    db_helper.update_job_status(job_id, "queued")
    background_tasks.add_task(run_migration_task, job_id)
    
    return {"message": "Migration queued for processing", "job_id": job_id}


def run_cleanup_task(job_id: str, reset: bool = False):
    """Background task to run the duplicate cleanup script (500 posts per batch)"""
    db_helper.update_job_status(job_id, "processing")

    backend_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(backend_dir)
    script_path = os.path.join(parent_dir, "cleanup_wp_duplicates.py")
    
    if os.path.exists(script_path):
        env = os.environ.copy()
        env["PYTHONWARNINGS"] = "ignore"
        try:
            venv_python = os.path.join(parent_dir, ".venv", "Scripts", "python.exe")
            if not os.path.exists(venv_python):
                venv_python = "python"
                
            cmd = [venv_python, script_path, "--batch-size", "500"]
            if reset:
                cmd.append("--reset")

            result = subprocess.run(
                cmd, 
                env=env, 
                cwd=parent_dir, 
                capture_output=True,
                text=True,
                check=True
            )
            out = result.stdout or ""
            match = re.search(r"Duplicates removed this run\s*:\s*(\d+)", out)
            cleaned_count = match.group(1) if match else "0"
            if "CLEANUP ENGINE COMPLETED" in out:
                summary = f"All post types finished! Removed {cleaned_count} duplicates in this batch."
            else:
                summary = f"Batch finished: {cleaned_count} duplicates moved to trash. Ready for next 500."

            db_helper.update_job_status(job_id, "completed", error=summary)
            print(f"Successfully ran cleanup script: {summary}")
        except subprocess.CalledProcessError as e:
            err_output = (e.stderr or "").strip()
            out_output = (e.stdout or "").strip()
            error_details = err_output if err_output else out_output
            if not error_details:
                error_details = f"Script failed with exit code {e.returncode}"
            else:
                if len(error_details) > 400:
                    error_details = "..." + error_details[-397:]
            db_helper.update_job_status(job_id, "failed", error_details)
            print(f"Error executing cleanup script: {e}")
        except Exception as e:
            db_helper.update_job_status(job_id, "failed", str(e))
            print(f"Error executing cleanup script: {e}")
    else:
        db_helper.update_job_status(job_id, "failed", "Cleanup script missing on server")
        print(f"Cleanup script missing at: {script_path}")


class CleanupRequest(BaseModel):
    reset: bool = False


@app.post("/api/cleanup")
async def trigger_cleanup(
    background_tasks: BackgroundTasks,
    request: CleanupRequest = None,
    username: str = Depends(get_current_user)
):
    job_id = "cleanup_wp_duplicates.py"
    
    # Check if there is an active job running for cleanup
    existing_job = db_helper.get_job_status(job_id)
    if existing_job and existing_job.get("status") in ["queued", "processing"]:
        raise HTTPException(
            status_code=400,
            detail="A duplicate cleanup job is already running. Please wait until it completes."
        )
        
    reset = request.reset if request else False
    db_helper.update_job_status(job_id, "queued")
    background_tasks.add_task(run_cleanup_task, job_id, reset)
    
    return {"message": "Cleanup job queued for processing (500 posts batch)", "job_id": job_id}


@app.get("/api/cleanup/status")
def get_cleanup_status(username: str = Depends(get_current_user)):
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(backend_dir)
    state_file = os.path.join(parent_dir, "output", "cleanup_state.json")
    state = {}
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            pass
    job = db_helper.get_job_status("cleanup_wp_duplicates.py") or {}
    return {
        "job": job,
        "state": state
    }



@app.post("/api/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), 
    username: str = Depends(get_current_user)
):
    valid_extensions = ["html", "csv", "xlsx", "xls", "json"]
    ext = file.filename.split('.')[-1].lower()
    
    if ext not in valid_extensions:
        raise HTTPException(status_code=400, detail="Unsupported file format")

    # Lock Check: check if there is an active job running for this filename
    existing_job = db_helper.get_job_status(file.filename)
    if existing_job and existing_job.get("status") in ["queued", "processing"]:
        raise HTTPException(
            status_code=400,
            detail=f"A job for '{file.filename}' is already running (status: {existing_job.get('status')}). Please wait until it completes."
        )

    # Save the file temporarily
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(backend_dir)
    upload_dir = os.path.join(parent_dir, "output", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Set initial job status and dispatch background processing task
    db_helper.update_job_status(file.filename, "queued")
    background_tasks.add_task(process_uploaded_file, file_path, file.filename)
    
    return {"message": "File uploaded and queued for processing", "filename": file.filename}

@app.get("/api/jobs")
def get_jobs_status(username: str = Depends(get_current_user)):
    return db_helper.get_all_jobs()

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

# Serve frontend static files
frontend_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

