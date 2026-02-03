# modules/db_pool.py
import os, pyodbc, threading

_CONN = None
_LOCK = threading.Lock()

def get_sql_conn():
    global _CONN
    if _CONN and getattr(_CONN, "connected", 1) == 1:
        return _CONN
    with _LOCK:
        if _CONN and getattr(_CONN, "connected", 1) == 1:
            return _CONN
        cs = os.getenv("SQLSERVER_CONN_STR") or (
            "DRIVER={ODBC Driver 17 for SQL Server};"
            "SERVER=10.0.0.20\\SQLYC;DATABASE=SkodaBot;"
            "UID=skodabot;PWD=Skodabot.2024;"
            "Pooling=Yes;MARS_Connection=Yes;"
        )
        _CONN = pyodbc.connect(cs, autocommit=False)
        return _CONN
