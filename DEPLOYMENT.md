# Railway Deployment Guide for ADAL UI

## Quick Deployment Steps

### Prerequisites
- GitHub repository connected
- Railway account (https://railway.app)
- Environment variables ready

### Method 1: Deploy via Railway Dashboard (Easiest)

1. **Go to Railway Dashboard**
   - Visit https://railway.app
   - Click "New Project"
   - Select "Deploy from GitHub repo"

2. **Connect Repository**
   - Authorize Railway to access your GitHub
   - Select `Devcavi19/adal_ui` repository
   - Choose the `feature/about` branch (or merge to `main` first)

3. **Configure Environment Variables**
   In the Railway dashboard, go to Variables tab and add:
   ```
   SUPABASE_URL=your_supabase_project_url
   SUPABASE_KEY=your_supabase_anon_key
   SUPABASE_SERVICE_KEY=your_supabase_service_role_key
   GOOGLE_API_KEY=your_google_gemini_api_key
   SECRET_KEY=your_flask_secret_key
   FLASK_ENV=production
   DEBUG=False
   ```

4. **Deploy**
   - Railway will automatically detect the Python app
   - It will install dependencies from `requirements.txt`
   - Start the app using the command in `Procfile`

5. **Get Your URL**
   - Railway will generate a public URL
   - Click "Settings" → "Generate Domain" if not auto-generated
   - Your app will be live at: `https://your-app-name.railway.app`

### Method 2: Deploy via Railway CLI

1. **Install Railway CLI**
   ```bash
   npm install -g @railway/cli
   ```

2. **Login to Railway**
   ```bash
   railway login
   ```

3. **Initialize Project**
   ```bash
   cd /workspaces/adal_ui
   railway init
   ```

4. **Set Environment Variables**
   ```bash
   railway variables set SUPABASE_URL="your_supabase_url"
   railway variables set SUPABASE_KEY="your_supabase_key"
   railway variables set SUPABASE_SERVICE_KEY="your_service_key"
   railway variables set GOOGLE_API_KEY="your_google_api_key"
   railway variables set SECRET_KEY="your_secret_key"
   railway variables set FLASK_ENV="production"
   railway variables set DEBUG="False"
   ```

5. **Deploy**
   ```bash
   railway up
   ```

6. **Open Your App**
   ```bash
   railway open
   ```

## Important Configuration Files Created

- ✅ `railway.toml` - Railway build and deploy configuration
- ✅ `Procfile` - Start command for the application
- ✅ `.env.example` - Template for environment variables
- ✅ `.railwayignore` - Files to exclude from deployment
- ✅ `runtime.txt` - Python version specification
- ✅ `requirements.txt` - Updated with gunicorn
- ✅ `run.py` - Updated for production with PORT binding

## Deployment Checklist

- [x] Create `railway.toml`
- [x] Create `Procfile`
- [x] Update `run.py` for production
- [x] Create `.env.example`
- [x] Create `.railwayignore`
- [x] Add `gunicorn` to `requirements.txt`
- [x] Create `runtime.txt`
- [ ] Push changes to GitHub
- [ ] Connect Railway to GitHub repo
- [ ] Set environment variables in Railway
- [ ] Deploy and test

## Before Your Presentation (9 AM)

1. **Merge feature branch to main** (recommended):
   ```bash
   git checkout main
   git merge feature/about
   git push origin main
   ```

2. **Or deploy directly from feature/about branch** in Railway settings

3. **Test these features**:
   - [ ] Homepage loads
   - [ ] Login/Signup works
   - [ ] Chat functionality works
   - [ ] RAG responses are generated
   - [ ] All static assets load (CSS, JS, images)

4. **Keep Railway Dashboard Open**:
   - Monitor deployment logs
   - Check for any errors
   - Note down the public URL for your presentation

## Troubleshooting

### If deployment fails:
1. Check Railway logs in the dashboard
2. Verify all environment variables are set
3. Ensure `index/` directory files are in the repo
4. Check that Python version matches (3.11.7)

### If app doesn't start:
1. Check that PORT environment variable is being used
2. Verify Supabase credentials are correct
3. Check Google API key is valid
4. Review application logs in Railway

## Post-Deployment

- Update `APP_URL` environment variable with your Railway URL
- Test all authentication flows
- Verify CORS settings allow Railway domain
- Monitor application logs for any issues

## Support

If you encounter issues:
1. Check Railway logs: `railway logs`
2. Check deployment status in Railway dashboard
3. Verify environment variables are correctly set
4. Test locally first with same environment variables

---

**Your app will be live within 2-5 minutes after deployment starts!**

Good luck with your 9 AM presentation! 🚀
