"""Initialize an empty database. Register users through the website.

No preset users or plaintext passwords are bundled for deployment.
"""
from cardiomate import init_db

if __name__ == "__main__":
    init_db()
    print("Database initialized. Open the website and register an account.")
