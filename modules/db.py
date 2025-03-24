# modules/db.py

import os
import logging
import pythoncom
import pyodbc
import win32com.client as win32

from dotenv import load_dotenv

# 1) .env dosyasını yükle
load_dotenv()

# 2) Gerekli tüm ortam değişkenlerini oku (hiç varsayılan vermiyoruz)
DB_SERVER = os.getenv("DB_SERVER")  
DB_NAME   = os.getenv("DB_NAME")    
DB_USER   = os.getenv("DB_USER")    
DB_PASS   = os.getenv("DB_PASS")    

# Eğer bu 4 değişken yoksa hata fırlat
if not all([DB_SERVER, DB_NAME, DB_USER, DB_PASS]):
    raise ValueError(
        "Database env variables missing! Please set DB_SERVER, DB_NAME, DB_USER, and DB_PASS in your .env file."
    )

def get_db_connection():
    """
    PyODBC ile MSSQL bağlantısı.
    .env dosyasından çekilen DB_SERVER, DB_NAME, DB_USER, DB_PASS kullanılır.
    """
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={DB_NAME};"
        f"UID={DB_USER};"
        f"PWD={DB_PASS};"
    )
    conn = pyodbc.connect(conn_str)
    return conn

def create_tables():
    """
    conversations ve cache_faq tablolarını oluşturur (yoksa).
    """
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
        );

        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='cache_faq' AND xtype='U')
        CREATE TABLE cache_faq (
            id INT IDENTITY(1,1) PRIMARY KEY,
            user_id NVARCHAR(255),
            question NVARCHAR(MAX),
            answer NVARCHAR(MAX),
            created_at DATETIME DEFAULT GETDATE()
        );
    ''')
    conn.commit()
    conn.close()

def save_to_db(user_id, question, answer, customer_answer=0):
    """
    conversations tablosuna yeni bir kayıt ekler.
    Eklenen satırın ID'sini döndürür.
    """
    logging.info("[DEBUG] save_to_db called -> user_id=%s, question=%s, answer_length=%d",
                 user_id, question, len(answer) if answer else 0)

    conn = get_db_connection()
    cursor = conn.cursor()
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
    Örneğin Like butonu için -> value = 1
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
    Outlook ile e-posta gönderen örnek fonksiyon (Windows ortamında).
    """
    logging.info("[MAIL] To: %s, Subject: %s", to_email, subject)
    pythoncom.CoInitialize()
    outlook = win32.Dispatch('outlook.application')
    mail = outlook.CreateItem(0)
    mail.Subject = subject
    mail.Body = body
    mail.To = to_email
    mail.Send()
    logging.info("[MAIL] Email sent successfully")
