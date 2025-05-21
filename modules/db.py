import pyodbc
import pythoncom
import win32com.client as win32
import logging

def get_db_connection():
    """
    pyodbc.connect() çağrısı tek bir string alır.
    Birden fazla argüman verirseniz "TypeError: function takes at most 1 argument" hatası alırsınız.
    Bu nedenle tüm parametreleri tek bir connection string içinde birleştiriyoruz.
    """
    conn = pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=10.0.0.20\\SQLYC;"
        "DATABASE=SkodaBot;"
        "UID=skodabot;"
        "PWD=Skodabot.2024;"
    )
    return conn

def create_tables():
    """
    1) 'conversations' tablosu yoksa oluştur.
    2) 'username' kolonu yoksa ekle.
    3) 'cache_faq' tablosu yoksa oluştur.
    4) 'username' kolonu yoksa ekle.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1) conversations tablosu
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

    # 2) conversations tablosuna 'username' kolonu ekle (yoksa)
    cursor.execute('''
        IF COL_LENGTH('conversations', 'username') IS NULL
        BEGIN
            ALTER TABLE [dbo].[conversations]
            ADD [username] NVARCHAR(255);
        END
    ''')

    # 3) cache_faq tablosu
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

    # 4) cache_faq tablosuna 'username' kolonu ekle (yoksa) -- Yukarıdaki CREATE içinde
    cursor.execute('''
        IF COL_LENGTH('cache_faq', 'username') IS NULL
        BEGIN
            ALTER TABLE [dbo].[cache_faq]
            ADD [username] NVARCHAR(255);
        END
    ''')

    conn.commit()
    conn.close()

def save_to_db(user_id, question, answer, username="", customer_answer=0):
    """
    'conversations' tablosuna kayıt atmak için.
    - username opsiyonel parametredir (varsayılan "" atadık).
    """
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
    conn.close()

    return new_id

def save_to_faq(user_id, username, question, answer, assistant_id=""):
    """
    'cache_faq' tablosuna kayıt atmak için (fuzzy cache vb. için).
    username'i de eklemek istiyorsanız parametre olarak geçmelisiniz.
    """
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
    conn.close()

def update_customer_answer(conversation_id, value):
    """
    'conversations' tablosundaki customer_answer sütununu günceller.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE [dbo].[conversations]
        SET [customer_answer] = ?
        WHERE [id] = ?
    ''', (value, conversation_id))
    conn.commit()
    conn.close()

def send_email(subject, body, to_email):
    """
    Örnek Outlook mail fonksiyonu. 
    """
    logging.info(f"[MAIL] To: {to_email}, Subject: {subject}, Body: {body}")
    pythoncom.CoInitialize()
    outlook = win32.Dispatch('outlook.application')
    mail = outlook.CreateItem(0)
    mail.Subject = subject
    mail.Body = body
    mail.To = to_email
    mail.Send()
    logging.info("[MAIL] Email sent successfully")