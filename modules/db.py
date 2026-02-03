import pyodbc
import pythoncom
import win32com.client as win32
import logging

from modules.trace_debug import traced_sql_conn


def get_db_connection():
    """
    Tek bir connection string ile bağlanır ve TRACE açıksa bağlantıyı wrap eder.
    """
    conn = pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=10.0.0.20\\SQLYC;"
        "DATABASE=SkodaBot;"
        "UID=skodabot;"
        "PWD=Skodabot.2024;"
        # İstersen: "TrustServerCertificate=yes;"
    )
    # ✅ TRACE: burada sarmala
    return traced_sql_conn(conn)


def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        IF NOT EXISTS (
            SELECT * FROM sys.objects
            WHERE object_id = OBJECT_ID(N'[dbo].[conversations]')
            AND type in (N'U')
        )
        CREATE TABLE [dbo].[conversations] (
            [id] INT IDENTITY(1,1) PRIMARY KEY,
            [user_id] NVARCHAR(255) NOT NULL,
            [question] NVARCHAR(MAX) NOT NULL,
            [answer] NVARCHAR(MAX) NOT NULL,
            [customer_answer] INT DEFAULT 0,
            [timestamp] DATETIME DEFAULT GETDATE()
        );
    ''')

    cursor.execute('''
        IF COL_LENGTH('conversations', 'username') IS NULL
        BEGIN
            ALTER TABLE [dbo].[conversations]
            ADD [username] NVARCHAR(255);
        END
    ''')

    cursor.execute('''
        IF NOT EXISTS (
            SELECT * FROM sys.objects
            WHERE object_id = OBJECT_ID(N'[dbo].[cache_faq]')
            AND type in (N'U')
        )
        CREATE TABLE [dbo].[cache_faq] (
            [id] INT IDENTITY(1,1) PRIMARY KEY,
            [user_id] NVARCHAR(255),
            [username] NVARCHAR(255),
            [question] NVARCHAR(MAX),
            [answer] NVARCHAR(MAX),
            [assistant_id] NVARCHAR(255),
            [created_at] DATETIME DEFAULT GETDATE()
        );
    ''')

    cursor.execute('''
        IF COL_LENGTH('cache_faq', 'username') IS NULL
        BEGIN
            ALTER TABLE [dbo].[cache_faq]
            ADD [username] NVARCHAR(255);
        END
    ''')

    conn.commit()
    cursor.close()
    conn.close()


def save_to_db(user_id, question, answer, username="", customer_answer=0):
    logging.info("[DEBUG] save_to_db called with ->")
    logging.info(f"user_id: {user_id} (type={type(user_id)})")
    logging.info(f"question: {question} (type={type(question)})")
    logging.info(f"answer: {answer} (type={type(answer)})")
    logging.info(f"username: {username} (type={type(username)})")
    logging.info(f"customer_answer: {customer_answer} (type={type(customer_answer)})")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO [dbo].[conversations]
            ([user_id], [question], [answer], [username], [customer_answer])
        OUTPUT Inserted.id
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, question, answer, username, customer_answer))

    new_id = cursor.fetchone()[0]
    conn.commit()

    cursor.close()
    conn.close()
    return new_id


def save_to_faq(user_id, username, question, answer, assistant_id=""):
    logging.info("[DEBUG] save_to_faq called with ->")
    logging.info(f"user_id: {user_id}")
    logging.info(f"username: {username}")
    logging.info(f"question: {question}")
    logging.info(f"answer: {answer}")
    logging.info(f"assistant_id: {assistant_id}")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO [dbo].[cache_faq]
            ([user_id], [username], [question], [answer], [assistant_id], [created_at])
        VALUES (?, ?, ?, ?, ?, GETDATE())
    ''', (user_id, username, question, answer, assistant_id))

    conn.commit()
    cursor.close()
    conn.close()


def update_customer_answer(conv_id, value):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE [dbo].[conversations]
        SET customer_answer = ?
        WHERE id = ?
    """, (value, conv_id))

    conn.commit()
    logging.info(f"[DEBUG] update_customer_answer -> conv_id={conv_id}, value={value}, rowcount={cursor.rowcount}")

    cursor.close()
    conn.close()


def send_email(subject, body, to_email):
    logging.info(f"[MAIL] To: {to_email}, Subject: {subject}, Body: {body}")
    pythoncom.CoInitialize()
    outlook = win32.Dispatch('outlook.application')
    mail = outlook.CreateItem(0)
    mail.Subject = subject
    mail.Body = body
    mail.To = to_email
    mail.Send()
    logging.info("[MAIL] Email sent successfully")
