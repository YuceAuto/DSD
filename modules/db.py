import pyodbc
import pythoncom
import win32com.client as win32
import logging

def get_db_connection():
    conn = pyodbc.connect(
        'DRIVER={ODBC Driver 17 for SQL Server};'
        'SERVER=10.0.0.20\\SQLYC;'
        'DATABASE=SkodaBot;'
        'UID=skodabot;'
        'PWD=Skodabot.2024;'
    )
    return conn

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
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
    conn.commit()
    conn.close()

def save_to_db(user_id, question, answer, customer_answer=0):
    """
    Eklenen satırın ID'sini döndürür.
    """
    logging.info("[DEBUG] save_to_db called with ->")
    logging.info(f"user_id: {user_id} (type={type(user_id)})")
    logging.info(f"question: {question} (type={type(question)})")
    logging.info(f"answer: {answer} (type={type(answer)})")
    logging.info(f"customer_answer: {customer_answer} (type={type(customer_answer)})")

    conn = get_db_connection()
    cursor = conn.cursor()

    # OUTPUT Inserted.id ile eklenen satırın kimlik (ID) değerini geri alıyoruz
    cursor.execute('''
        INSERT INTO conversations (user_id, question, answer, customer_answer)
        OUTPUT Inserted.id
        VALUES (?, ?, ?, ?)
    ''', (user_id, question, answer, customer_answer))

    new_id = cursor.fetchone()[0]  # Eklenen satırın ID'si
    conn.commit()
    conn.close()

    return new_id

def update_customer_answer(conversation_id, value):
    """
    Mevcut kaydın customer_answer değerini günceller.
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
    logging.info(f"[MAIL] To: {to_email}, Subject: {subject}, Body: {body}")
    pythoncom.CoInitialize()
    outlook = win32.Dispatch('outlook.application')
    mail = outlook.CreateItem(0)
    mail.Subject = subject
    mail.Body = body
    mail.To = to_email
    mail.Send()
    logging.info("[MAIL] Email sent successfully")
