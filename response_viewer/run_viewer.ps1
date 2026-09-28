$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
uv run --with "streamlit>=1.50,<2" streamlit run app.py
