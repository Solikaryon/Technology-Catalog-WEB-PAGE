"""Simple helper to verify the Application Name sent to SQL Server.

Usage:
    set APP_NAME=MiAppName   (Windows CMD)
    $env:APP_NAME = 'MiAppName'  (PowerShell)
    python verify_app_name.py

It prints the local `APP_NAME` value and the result of `SELECT APP_NAME()` from SQL Server.
"""
from db import APP_NAME, get_connection

print('Local APP_NAME:', repr(APP_NAME))
try:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT APP_NAME()')
    row = cur.fetchone()
    print('Server APP_NAME():', row)
    cur.close()
    conn.close()
except Exception as e:
    print('Error during verification:', e)
    raise
