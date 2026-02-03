# UrunBot → MSSQL Bilgi Tabanı (KB)

**Amaç:** Uygulamanın dosyaları doğrudan okuması yerine, bütün içeriklerin MSSQL'e aktarılması ve buradan okunması.

## Neden daha doğru?
- **Türkçe FTS ile arama:** SQL Server Full‑Text Search (LCID 1055) başlık ve gövdeye ağırlık verir; `LIKE`'a göre daha isabetli.
- **Tipli alanlar:** Fiyat vb. sayıları `DECIMAL` olarak saklarız—bölgesel format hatalarını önler.
- **Sürüm/tekrar kontrolü:** Her belge içerik hash'i ile kaydedilir; çift kayıtların önüne geçilir.
- **Tek kaynak:** `static/kb/*.md` + `modules/data/*_data.py` & `*_teknik.py` aynı şemada birleşir.

## Kurulum

1. **ODBC ve Python kütüphaneleri**
   ```bash
   pip install pyodbc python-dotenv
   ```
   Windows için *ODBC Driver 17/18 for SQL Server* kurulu olmalı.

2. **Şema**
   `sql/01_kb_schema.sql` dosyasını veritabanınızda çalıştırın. Full‑Text KEY INDEX adında sorun olursa PK adını
   `SELECT i.name FROM sys.indexes i JOIN sys.tables t ON i.object_id=t.object_id WHERE t.name='Chunk' AND is_primary_key=1 AND SCHEMA_NAME(t.schema_id)='kb'`
   ile bulun ve komutu buna göre düzenleyin.

3. **Bağlantı dizesi**
   ```powershell
   setx MSSQL_CONN_STR "DRIVER={ODBC Driver 17 for SQL Server};SERVER=10.0.0.20\SQLYC;DATABASE=SkodaBot;UID=skodabot;PWD=***;TrustServerCertificate=Yes"
   ```

4. **Yükleme**
   ```bash
   python scripts/ingest_to_mssql.py --repo-root "C:\path\to\UrunBot" --drop-and-recreate 1
   ```

5. **Uygulamadan okuma (örnek)**
   ```python
   from modules.kb_repo import MSSQLKb
   kb = MSSQLKb()
   hits = kb.search_chunks("Octavia bagaj hacmi", top_k=5, model_hint="Octavia")
   options = kb.get_options("Octavia", trim="Elite")
   ```
