# AGIRA Contract Viewer

A standalone, read-only Streamlit viewer for parsed AGIRA response JSON. It is
deliberately separate from the daily pipeline: it does not import pipeline code,
write to pipeline folders, or trigger any jobs. It only reads the archived RESP
files in `data/history/interrogations/resp/`.

## Start it

From PowerShell:

```powershell
.\response_viewer\run_viewer.ps1
```

The first launch may take a moment while `uv` downloads Streamlit. You can also
install it explicitly and run the app yourself:

```powershell
uv pip install -r response_viewer\requirements.txt
uv run streamlit run response_viewer\app.py
```

## Browse and filter

Every `*.json` in `data/history/interrogations/resp/YYYY-MM-DD/` is listed in
the sidebar, newest day first. Type a **Numéro de police** (case-insensitive,
partial match allowed) to keep only the files that contain it and only the
matching contracts inside the selected file.

You can still drag extra `.json` response files into the uploader. They stay in
memory for the Streamlit session and are never copied, changed, or persisted.

Run the model tests with `uv run pytest response_viewer/test_model.py`.
