# -*- coding: utf-8 -*-
import os, pyodbc

class MSSQLKb:
    def __init__(self, conn_str: str = None):
        self.conn_str = conn_str or os.getenv('MSSQL_CONN_STR')
        if not self.conn_str:
            raise RuntimeError('MSSQL_CONN_STR yok.')
        self.conn = pyodbc.connect(self.conn_str)

    def search_chunks(self, query: str, top_k: int = 8, model_hint: str = None):
        q = query.strip(); cur = self.conn.cursor()
        try:
            if model_hint:
                cur.execute("""
                    SELECT TOP (?) c.chunk_id, c.doc_id, c.section_h2, c.section_h3, c.content_txt, ft.[RANK] AS score
                    FROM CONTAINSTABLE(kb.Chunk, (content, content_txt, section_h2, section_h3), ?) ft
                    JOIN kb.Chunk c ON c.chunk_id = ft.[KEY]
                    JOIN kb.Document d ON d.doc_id = c.doc_id
                    WHERE d.model_name = ?
                    ORDER BY ft.[RANK] DESC;
                """, (top_k, q, model_hint))
            else:
                cur.execute("""
                    SELECT TOP (?) c.chunk_id, c.doc_id, c.section_h2, c.section_h3, c.content_txt, ft.[RANK] AS score
                    FROM CONTAINSTABLE(kb.Chunk, (content, content_txt, section_h2, section_h3), ?) ft
                    JOIN kb.Chunk c ON c.chunk_id = ft.[KEY]
                    ORDER BY ft.[RANK] DESC;
                """, (top_k, q))
            rows = cur.fetchall()
            return [{
                'chunk_id': r[0], 'doc_id': r[1], 'section_h2': r[2], 'section_h3': r[3],
                'snippet': r[4], 'score': float(r[5])
            } for r in rows]
        except Exception:
            patt = f"%{q}%"
            if model_hint:
                cur.execute("""
                    SELECT TOP (?) c.chunk_id, c.doc_id, c.section_h2, c.section_h3, c.content_txt, 0.0
                    FROM kb.Chunk c
                    JOIN kb.Document d ON d.doc_id = c.doc_id
                    WHERE (c.content_txt LIKE ? OR c.content LIKE ?) AND d.model_name = ?
                    ORDER BY c.doc_id, c.ord;
                """, (top_k, patt, patt, model_hint))
            else:
                cur.execute("""
                    SELECT TOP (?) c.chunk_id, c.doc_id, c.section_h2, c.section_h3, c.content_txt, 0.0
                    FROM kb.Chunk c
                    WHERE (c.content_txt LIKE ? OR c.content LIKE ?)
                    ORDER BY c.doc_id, c.ord;
                """, (top_k, patt, patt))
            rows = cur.fetchall()
            return [{
                'chunk_id': r[0], 'doc_id': r[1], 'section_h2': r[2], 'section_h3': r[3],
                'snippet': r[4], 'score': float(r[5])
            } for r in rows]

    def get_options(self, model: str, trim: str = None):
        cur = self.conn.cursor()
        if trim:
            cur.execute("""
                SELECT code, description, price_net, price_at_80, price_at_90
                FROM kb.OptionItem
                WHERE model_name=? AND ISNULL(trim_name,'')=ISNULL(?, '')
                ORDER BY code;
            """, (model, trim))
        else:
            cur.execute("""
                SELECT code, description, price_net, price_at_80, price_at_90
                FROM kb.OptionItem
                WHERE model_name=?
                ORDER BY trim_name, code;
            """, (model,))
        rows = cur.fetchall()
        return [{
            'code': r[0], 'description': r[1],
            'price_net': float(r[2]) if r[2] is not None else None,
            'price_at_80': float(r[3]) if r[3] is not None else None,
            'price_at_90': float(r[4]) if r[4] is not None else None
        } for r in rows]
