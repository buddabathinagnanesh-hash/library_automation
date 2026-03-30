import sys
import os

# Ensure the parent directory is in the path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'library_system')))

from library_system.app import app

if __name__ == "__main__":
    # Ensure instance folder exists
    os.makedirs(os.path.join('library_system', 'instance'), exist_ok=True)
    
    # Run the app
    app.run(host="0.0.0.0", port=5000, debug=True)
