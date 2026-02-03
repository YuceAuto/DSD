IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'kb')
    EXEC('CREATE SCHEMA kb');

IF OBJECT_ID('kb.Document','U') IS NULL
BEGIN
    CREATE TABLE kb.Document(
        doc_id       INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        source_path  NVARCHAR(400)    NOT NULL,
        source_type  NVARCHAR(30)     NOT NULL,
        model_name   NVARCHAR(50)     NULL,
        trim_name    NVARCHAR(50)     NULL,
        title        NVARCHAR(200)    NULL,
        version_tag  NVARCHAR(50)     NULL,
        lang         NVARCHAR(10)     NOT NULL CONSTRAINT DF_kb_Document_lang DEFAULT('tr'),
        content_hash VARBINARY(32)    NOT NULL,
        created_at   DATETIME2(3)     NOT NULL CONSTRAINT DF_kb_Document_created DEFAULT SYSUTCDATETIME()
    );
    CREATE UNIQUE INDEX UX_kb_Document_src_hash ON kb.Document(source_path, content_hash);
END

IF OBJECT_ID('kb.Chunk','U') IS NULL
BEGIN
    CREATE TABLE kb.Chunk(
        chunk_id     BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        doc_id       INT NOT NULL CONSTRAINT FK_kb_Chunk_Document REFERENCES kb.Document(doc_id) ON DELETE CASCADE,
        ord          INT NOT NULL,
        section_h2   NVARCHAR(200) NULL,
        section_h3   NVARCHAR(200) NULL,
        content      NVARCHAR(MAX) NOT NULL,
        content_txt  NVARCHAR(MAX) NULL,
        tokens_guess INT NULL
    );
    CREATE UNIQUE INDEX UX_kb_Chunk_doc_ord ON kb.Chunk(doc_id, ord);
END

IF NOT EXISTS (SELECT 1 FROM sys.fulltext_catalogs WHERE name = N'ft_kb')
BEGIN
    CREATE FULLTEXT CATALOG ft_kb AS DEFAULT;
END

-- Not: KEY INDEX satırında PK adını gerekirse manuel belirtiniz (README).
-- Aşağıdaki komut bazı kurulumlarda direkt çalışır, çalışmazsa README'deki yönergeyi uygulayın.
IF NOT EXISTS (
    SELECT 1 FROM sys.fulltext_indexes fi
    JOIN sys.objects o ON o.object_id = fi.object_id
    WHERE o.name = N'Chunk' AND SCHEMA_NAME(o.schema_id) = N'kb'
)
BEGIN
    CREATE FULLTEXT INDEX ON kb.Chunk
    (
        content     LANGUAGE 1055,
        content_txt LANGUAGE 1055,
        section_h2  LANGUAGE 1055,
        section_h3  LANGUAGE 1055
    )
    KEY INDEX [PK__Chunk__] ON ft_kb WITH CHANGE_TRACKING AUTO;
END

IF OBJECT_ID('kb.TableRegistry','U') IS NULL
BEGIN
    CREATE TABLE kb.TableRegistry(
        table_id     BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        doc_id       INT NOT NULL CONSTRAINT FK_kb_TableRegistry_Document REFERENCES kb.Document(doc_id) ON DELETE CASCADE,
        section_h2   NVARCHAR(200) NULL,
        title        NVARCHAR(200) NULL,
        col_schema   NVARCHAR(MAX) NULL,
        row_count    INT NULL
    );
END

IF OBJECT_ID('kb.TableRow','U') IS NULL
BEGIN
    CREATE TABLE kb.TableRow(
        table_id     BIGINT NOT NULL CONSTRAINT FK_kb_TableRow_TableRegistry REFERENCES kb.TableRegistry(table_id) ON DELETE CASCADE,
        row_no       INT    NOT NULL,
        col_name     NVARCHAR(200) NOT NULL,
        col_value    NVARCHAR(MAX) NULL,
        CONSTRAINT PK_kb_TableRow PRIMARY KEY (table_id, row_no, col_name)
    );
END

IF OBJECT_ID('kb.OptionItem','U') IS NULL
BEGIN
    CREATE TABLE kb.OptionItem(
        option_id       BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        model_name      NVARCHAR(50) NOT NULL,
        trim_name       NVARCHAR(50) NULL,
        code            NVARCHAR(50) NOT NULL,
        description     NVARCHAR(400) NULL,
        price_net       DECIMAL(18,2) NULL,
        price_at_80     DECIMAL(18,2) NULL,
        price_at_90     DECIMAL(18,2) NULL,
        doc_id          INT NULL CONSTRAINT FK_kb_OptionItem_Document REFERENCES kb.Document(doc_id) ON DELETE SET NULL,
        table_id        BIGINT NULL CONSTRAINT FK_kb_OptionItem_TableRegistry REFERENCES kb.TableRegistry(table_id) ON DELETE SET NULL,
        CONSTRAINT UX_kb_OptionItem UNIQUE(model_name, ISNULL(trim_name,''), code)
    );
    CREATE INDEX IX_kb_OptionItem_model ON kb.OptionItem(model_name, trim_name);
END
