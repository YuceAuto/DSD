import pyodbc
import pythoncom
import win32com.client as win32
import logging

def get_db_connection():
    """
    SQL Server'a bağlanmak için kullanılan fonksiyon.
    Bağlantı bilgilerini kendi sunucu/DB kullanıcı/parolanıza göre düzenleyin.
    """
    conn = pyodbc.connect(
        'DRIVER={ODBC Driver 17 for SQL Server};'
        'SERVER=10.0.0.20\\SQLYC;'
        'DATABASE=SkodaBot;'
        'UID=skodabot;'
        'PWD=Skodabot.2024;'
    )
    return conn

def create_tables():
    """
    - Eğer 'conversations' tablosu yoksa oluşturur,
    - Ayrıca 'username' kolonu yoksa ekler.
    - 'cache_faq' tablosu yoksa onu da oluşturur.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1) conversations tablosu yoksa oluştur
    cursor.execute('''
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='conversations' AND xtype='U')
        CREATE TABLE conversations (
            id INT IDENTITY(1,1) PRIMARY KEY,
            user_id NVARCHAR(255) NOT NULL,
            question NVARCHAR(MAX) NOT NULL,
            answer NVARCHAR(MAX) NOT NULL,
            customer_answer INT DEFAULT 0,
            timestamp DATETIME DEFAULT GETDATE()
        )
    ''')

    # 2) 'username' kolonu yoksa ekle
    cursor.execute('''
        IF COL_LENGTH('conversations', 'username') IS NULL
        BEGIN
            ALTER TABLE conversations
            ADD username NVARCHAR(255)
        END
    ''')

    # 3) cache_faq tablosu (önbellek)
    cursor.execute('''
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='cache_faq' AND xtype='U')
        CREATE TABLE cache_faq (
            id INT IDENTITY(1,1) PRIMARY KEY,
            user_id NVARCHAR(255),
            question NVARCHAR(MAX),
            answer NVARCHAR(MAX),
            created_at DATETIME DEFAULT GETDATE()
        )
    ''')

    conn.commit()
    conn.close()

def save_to_db(user_id, username, question, answer, customer_answer=0):
    """
    'username' parametresini de DB'ye kaydediyoruz.
    'conversations' tablosunda 'username' kolonu olduğuna dikkat edin.
    """
    logging.info("[DEBUG] save_to_db called with ->")
    logging.info(f"user_id: {user_id} (type={type(user_id)})")
    logging.info(f"username: {username} (type={type(username)})")
    logging.info(f"question: {question} (type={type(question)})")
    logging.info(f"answer: {answer} (type={type(answer)})")
    logging.info(f"customer_answer: {customer_answer} (type={type(customer_answer)})")

    conn = get_db_connection()
    cursor = conn.cursor()

    # INSERT cümlesinde username'i de ekledik
    cursor.execute('''
        INSERT INTO conversations (user_id, username, question, answer, customer_answer)
        OUTPUT Inserted.id
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, username, question, answer, customer_answer))

    new_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    return new_id

def update_customer_answer(conversation_id, value):
    """
    Kullanıcının beğeni veya beğenmeme (customer_answer) değerini günceller.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE conversations
        SET customer_answer = ?
        WHERE id = ?
    ''', (value, conversation_id))
    conn.commit()
    conn.close()

def send_email(subject, body, to_email):
    """
    Örnek Outlook mail fonksiyonu. Proje içerisinde kullanıyorsanız aktif hale getirebilirsiniz.
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
