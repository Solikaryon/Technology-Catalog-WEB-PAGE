from app import app
import webbrowser
from threading import Timer


def _open_browser():
    try:
        webbrowser.open_new('http://0.0.0.0:5000') # Open the app in the default web browser
    except Exception:
        pass


if __name__ == '__main__':
    # Delay slightly so the server finishes starting before opening the browser
    Timer(1.0, _open_browser).start()
    # Run the Flask app without the reloader so PyInstaller's single executable
    # doesn't spawn multiple processes. Keep debug=False for production-like run.
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
