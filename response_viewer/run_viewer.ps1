$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
uv run --extra viewer streamlit run app.py
