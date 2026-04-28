"""
Application entry point.
"""
import os

from dotenv import load_dotenv

# Load .env before importing anything that reads config
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from app import create_app  # noqa: E402

app = create_app()


def main() -> None:
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('FLASK_DEBUG', '0') == '1',
        use_reloader=False, 
        threaded=True,        
    )


if __name__ == '__main__':
    main()
