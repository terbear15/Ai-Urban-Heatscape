"""Compile the Python dashboard to a static Panel/Pyodide application."""
import os
from pathlib import Path
from panel.io.convert import convert_app

HERE = Path(__file__).resolve().parent
os.chdir(HERE)
convert_app('app.py', dest_path='../dist/explorer', requirements=['numpy'],
            resources=['routing.py', 'search.py', 'data/philadelphia.json.gz'],
            runtime='pyodide-worker', prerender=False)
