"""WSGI entry point.

    python -m flask --app wsgi run --debug     # development
    gunicorn wsgi:app                          # production
"""

from secret_hitler import create_app

app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
