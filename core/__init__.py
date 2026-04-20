import os
from flask import Flask

def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'default_secret_key')

    # Register routes (blueprint) and initialize environment
    from .routes import main_bp, init_env
    init_env()
    
    app.register_blueprint(main_bp)

    return app