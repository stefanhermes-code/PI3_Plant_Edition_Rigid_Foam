@echo off
title PI3 Plant Edition - Streamlit App
cd /d "%~dp0"

echo Checking/installing required packages...
pip install -r requirements.txt

echo.
echo Starting PI3 Plant Edition...
echo (Uses a local SQLite file, pi3_local.db, unless DATABASE_URL is set
echo  in .streamlit\secrets.toml - see README.md for the Supabase setup.)
echo.
streamlit run app.py

echo.
echo App has stopped. Press any key to close this window.
pause >nul
