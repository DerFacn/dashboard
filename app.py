from core import create_app

# This instance is picked up by Gunicorn (app:app)
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)