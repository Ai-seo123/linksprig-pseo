# LinkSprig Engine (pSEO WordPress Pipeline)

A full-stack AI-driven programmatic SEO (pSEO) pipeline for generating and directly importing content into WordPress. Features a Python FastAPI backend for handling file processing (HTML, CSV, Excel) and a sleek React (Vite) dashboard interface built with a glassmorphism design.

## Features
- **File Uploads**: Easily drop HTML, CSV, or Excel files into the queue.
- **Real-Time Job Status**: Tracks in-progress and finished background processing tasks.
- **Simulated CAPTCHA Verification**: Locally bypassable CAPTCHA for secure entry.
- **Direct WordPress Integration**: Automatic categories setup and post draft creations via the WordPress REST API.

---

## 🚀 How to Host on Render

This repository includes a `render.yaml` Blueprint file for automatic one-click configuration of both the **FastAPI Backend** and the **Vite React Frontend**.

### Step 1: Create a GitHub Repository
1. Go to [GitHub](https://github.com/) and create a new repository (e.g., `linksprig-pseo`). Keep it public or private.
2. In your local project directory terminal (`C:\Users\ARNAV\.gemini\antigravity\scratch\linksprig-pseo`), run the following commands to link and push your code:
   ```bash
   git remote add origin https://github.com/<your-username>/linksprig-pseo.git
   git branch -M main
   git push -u origin main
   ```

### Step 2: Deploy to Render
1. Log in to [Render](https://render.com/).
2. Click **New +** in the top-right corner and select **Blueprint**.
3. Connect your GitHub account and select the **`linksprig-pseo`** repository.
4. Render will read the `render.yaml` file and automatically configure both services:
   - **`linksprig-backend`** (Python Web Service)
   - **`linksprig-frontend`** (Static Site)
5. Fill in the required environment variables in the Render dashboard for `linksprig-backend`:
   - `ADMIN_PASSWORD_HASH`: The bcrypt hash for your admin password.
   - `WP_URL`: Your WordPress website URL (e.g., `https://example.com`).
   - `WP_USER`: Your WordPress username.
   - `WP_APP_PASSWORD`: Your WordPress Application Password.
   - `GEMINI_API_KEY`: Your Google Gemini API Key.
6. Click **Apply** to deploy both services. Render will automatically link the frontend static site to your backend API.
