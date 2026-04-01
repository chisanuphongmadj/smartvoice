@echo off
title SmartVoice
call .venv\Scripts\activate
streamlit run app.py --server.port 8501
pause
