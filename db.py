import os
import pyodbc

# Database credentials used by the application. Kept here so admin validation can check them.
SERVER = "MXGDLM0NXSQLV1A"
DATABASE = "Tecnologias"
UID = "Fujiadmin"
PWD = "Fujidb213$"
DRIVER = "ODBC Driver 17 for SQL Server"

# Application name to appear in SQL Server traces/profiler. Can be overridden
# with the environment variable `APP_NAME`. Leave empty to skip.
APP_NAME = os.getenv('APP_NAME', 'Flask_Tecnologias')


def get_connection():
    """Return a pyodbc connection. Includes optional `Application Name` and
    provides a clearer error message on failure so the app doesn't crash with
    an obscure pyodbc exception when the connection string is mis-built.
    """
    conn_str = (
        f"DRIVER={{{DRIVER}}};"
        f"SERVER={SERVER};"
        f"DATABASE={DATABASE};"
        f"UID={UID};"
        f"PWD={PWD};"
    )
    if APP_NAME:
        # `Application Name` is the canonical key understood by SQL Server ODBC drivers
        # Some ODBC driver versions also accept `APP` — include both to maximize
        # compatibility with different clients / driver configs.
        conn_str += f"Application Name={APP_NAME};APP={APP_NAME};"
    try:
        return pyodbc.connect(conn_str)
    except Exception as e:  # pragma: no cover - runtime error handling
        # Re-raise a RuntimeError with the original message plus the built conn string
        # but avoid leaking the password in logs: redact the PWD value.
        safe_conn = conn_str.replace(PWD, '***REDACTED***')
        raise RuntimeError(f"Error conectando a la base de datos: {e}. Conn: {safe_conn}") from e


def validate_admin(db_name, user, password):
    """Simple validation: check provided credentials against the configured ones.

    Returns True if they match (case-sensitive for password), False otherwise.
    """
    try:
        if str(db_name).strip() == DATABASE and str(user).strip() == UID and str(password) == PWD:
            return True
    except Exception:
        pass
    return False


# Application-level admin users (internal to the app, separate from DB credentials)
APP_ADMINS = {
    'TruenaBecarios': 'Becarios763',
    'Machine Support': 'MSJabil159;'
}


def validate_app_admin(user, password):
    """Validate against internal application admin users.

    Username matching is case-sensitive for now to match the user's request.
    """
    try:
        if user in APP_ADMINS and APP_ADMINS[user] == password:
            return True
    except Exception:
        pass
    return False
