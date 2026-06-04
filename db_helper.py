import os
import json
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = "linksprig_seo"
REGISTRY_PATH = os.path.join("output", "generated_registry.json")
JOBS_PATH = os.path.join("output", "jobs_status.json")

_mongo_client = None
_db = None
_use_mongo = False

if MONGO_URI:
    try:
        # Connect to MongoDB with a 5 second timeout
        _mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        _mongo_client.admin.command('ping')
        _db = _mongo_client[DB_NAME]
        _use_mongo = True
        print("[DB] Connected successfully to MongoDB.")
    except Exception as e:
        print(f"[DB] [Warning] Failed to connect to MongoDB: {e}. Falling back to local storage.")
        _use_mongo = False
else:
    print("[DB] MONGO_URI not found. Falling back to local storage.")


# --- SLUG REGISTRY METHODS ---

def get_all_registered_slugs() -> set:
    """Fetch all registered slugs from MongoDB or local JSON fallback"""
    if _use_mongo:
        try:
            slugs = _db["slugs"].find({}, {"_id": 1})
            return {doc["_id"] for doc in slugs}
        except Exception as e:
            print(f"[DB] [Error] MongoDB query failed in get_all_registered_slugs: {e}. Falling back to local.")
            
    # Local JSON fallback
    if os.path.exists(REGISTRY_PATH):
        try:
            with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            print(f"[DB] [Warning] Failed to read local registry: {e}")
    return set()


def register_slug(slug: str) -> bool:
    """Register a slug incrementally in MongoDB or local JSON fallback"""
    if not slug:
        return False
        
    registered = False
    if _use_mongo:
        try:
            _db["slugs"].update_one(
                {"_id": slug},
                {"$set": {"slug": slug, "registered_at": datetime.utcnow()}},
                upsert=True
            )
            registered = True
        except Exception as e:
            print(f"[DB] [Error] MongoDB update failed in register_slug: {e}. Falling back to local.")
            
    # Local JSON fallback (always update local file if MongoDB is unavailable or fails)
    try:
        os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
        slugs = set()
        if os.path.exists(REGISTRY_PATH):
            try:
                with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                    slugs = set(json.load(f))
            except Exception:
                pass
        slugs.add(slug)
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(list(slugs), f, indent=2)
        return True
    except Exception as e:
        print(f"[DB] [Error] Failed to write local registry: {e}")
        return registered


# --- JOB TRACKING METHODS ---

def get_job_status(filename: str) -> dict:
    """Get status of a specific background processing job"""
    if _use_mongo:
        try:
            doc = _db["jobs"].find_one({"_id": filename})
            if doc:
                return {"status": doc.get("status"), "error": doc.get("error")}
            return None
        except Exception as e:
            print(f"[DB] [Error] MongoDB query failed in get_job_status: {e}. Falling back to local.")

    # Local fallback
    jobs = _load_local_jobs()
    return jobs.get(filename)


def update_job_status(filename: str, status: str, error: str = None) -> bool:
    """Update background processing job status"""
    updated = False
    if _use_mongo:
        try:
            _db["jobs"].update_one(
                {"_id": filename},
                {
                    "$set": {
                        "filename": filename,
                        "status": status,
                        "error": error,
                        "updated_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            updated = True
        except Exception as e:
            print(f"[DB] [Error] MongoDB update failed in update_job_status: {e}. Falling back to local.")

    # Local fallback
    try:
        jobs = _load_local_jobs()
        jobs[filename] = {"status": status, "error": error}
        _save_local_jobs(jobs)
        return True
    except Exception as e:
        print(f"[DB] [Error] Failed to update local jobs status: {e}")
        return updated


def get_all_jobs() -> dict:
    """Fetch status for all background jobs"""
    if _use_mongo:
        try:
            jobs = _db["jobs"].find()
            return {
                doc["_id"]: {"status": doc.get("status"), "error": doc.get("error")}
                for doc in jobs
            }
        except Exception as e:
            print(f"[DB] [Error] MongoDB query failed in get_all_jobs: {e}. Falling back to local.")

    # Local fallback
    return _load_local_jobs()


def clean_stale_jobs() -> int:
    """Reset jobs stuck in queued or processing status to failed on startup"""
    stale_count = 0
    if _use_mongo:
        try:
            result = _db["jobs"].update_many(
                {"status": {"$in": ["queued", "processing"]}},
                {
                    "$set": {
                        "status": "failed",
                        "error": "Server restarted during processing.",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            stale_count = result.modified_count
            if stale_count > 0:
                print(f"[DB] Cleaned up {stale_count} stale MongoDB jobs.")
        except Exception as e:
            print(f"[DB] [Error] MongoDB update failed in clean_stale_jobs: {e}.")

    # Always check local fallback too
    try:
        jobs = _load_local_jobs()
        local_modified = False
        for filename, job in jobs.items():
            if job.get("status") in ["queued", "processing"]:
                job["status"] = "failed"
                job["error"] = "Server restarted during processing."
                stale_count += 1
                local_modified = True
        if local_modified:
            _save_local_jobs(jobs)
            print(f"[DB] Cleaned up stale local jobs.")
    except Exception as e:
        print(f"[DB] [Error] Failed to clean local stale jobs: {e}")

    return stale_count


# --- LOCAL FILE HELPERS ---

def _load_local_jobs() -> dict:
    if os.path.exists(JOBS_PATH):
        try:
            with open(JOBS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_local_jobs(jobs: dict):
    try:
        os.makedirs(os.path.dirname(JOBS_PATH), exist_ok=True)
        with open(JOBS_PATH, "w", encoding="utf-8") as f:
            json.dump(jobs, f, indent=2)
    except Exception as e:
        print(f"[DB] [Error] Failed to save jobs locally: {e}")
