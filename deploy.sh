#!/bin/bash

# Railway Deployment Script for ADAL UI
# This script helps you deploy your app to Railway quickly

echo "🚀 ADAL UI - Railway Deployment Helper"
echo "========================================"
echo ""

# Check if railway CLI is installed
if ! command -v railway &> /dev/null
then
    echo "❌ Railway CLI not found. Installing..."
    npm install -g @railway/cli
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install Railway CLI. Please install Node.js first."
        echo "   Visit: https://nodejs.org/"
        exit 1
    fi
    echo "✅ Railway CLI installed successfully!"
else
    echo "✅ Railway CLI is already installed"
fi

echo ""
echo "📋 Pre-deployment checklist:"
echo "   - All environment variables ready? (Supabase, Google API)"
echo "   - Code tested locally?"
echo "   - Ready to deploy?"
echo ""

read -p "Continue with deployment? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    echo "Deployment cancelled."
    exit 0
fi

echo ""
echo "🔐 Logging into Railway..."
railway login

if [ $? -ne 0 ]; then
    echo "❌ Login failed. Please try again."
    exit 1
fi

echo ""
echo "🎯 Initializing Railway project..."
railway init

echo ""
echo "⚙️  Now you need to set your environment variables."
echo "    You can either:"
echo "    1. Set them via CLI (run the commands below)"
echo "    2. Set them in Railway dashboard (easier)"
echo ""
echo "CLI Commands to set variables:"
echo '  railway variables set SUPABASE_URL="your_value"'
echo '  railway variables set SUPABASE_KEY="your_value"'
echo '  railway variables set SUPABASE_SERVICE_KEY="your_value"'
echo '  railway variables set GOOGLE_API_KEY="your_value"'
echo '  railway variables set SECRET_KEY="your_value"'
echo '  railway variables set FLASK_ENV="production"'
echo '  railway variables set DEBUG="False"'
echo ""

read -p "Have you set all environment variables? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    echo "⚠️  Please set environment variables first, then run: railway up"
    exit 0
fi

echo ""
echo "🚀 Deploying to Railway..."
railway up

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Deployment successful!"
    echo ""
    echo "🌐 Opening your app..."
    railway open
    echo ""
    echo "📊 View logs: railway logs"
    echo "⚙️  View settings: railway open (then click Settings)"
else
    echo ""
    echo "❌ Deployment failed. Check the logs above."
    echo "   Try: railway logs"
fi
