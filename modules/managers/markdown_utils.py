import re

class MarkdownProcessor:
    # ---------- Yardımcılar ----------
    def _split_preserve_inner_blanks(self, line: str):
        """'| hücre |' baş/son boş hücrelerini at, içteki boşlukları koru."""
        parts = [c.strip() for c in line.split("|")]
        if parts and parts[0] == "":
            parts = parts[1:]
        if parts and parts[-1] == "":
            parts = parts[:-1]
        return parts

    def fix_table_characters(self, table_markdown: str) -> str:
        """Tablo içindeki karakter kaçmalarını giderir (PDF/artifacts)."""
        fixed_lines = []
        for line in table_markdown.split("\n"):
            if '|' not in line:
                fixed_lines.append(line)
                continue
            cols = line.split('|')
            clean = []
            for c in cols:
                c = c.strip()
                c = c.replace('**', '').replace('*', '')
                c = re.sub(r"(\d)''(\d)", r'\1/\2', c)
                c = re.sub(r"([A-Za-z])//([A-Za-z])", r"\1'\2", c)
                clean.append(c)
            fixed_lines.append(' | '.join(clean))
        return '\n'.join(fixed_lines)

    def markdown_table_to_html(self, md_table_str: str) -> str:
        """Markdown tablo bloğunu HTML tabloya çevirir."""
        md_table_str = self.fix_table_characters(md_table_str)
        lines = [ln for ln in md_table_str.strip().split("\n") if ln.strip()]
        if len(lines) < 2:
            return f"<p>{md_table_str}</p>"

        header_cols = self._split_preserve_inner_blanks(lines[0])
        num_cols = len(header_cols)

        html = '<table class="table table-bordered table-sm my-blue-table">\n'
        html += '<thead><tr>'
        for col in header_cols:
            html += f'<th>{col}</th>'
        html += '</tr></thead>\n<tbody>\n'

        # 2. satır ayraç kabul edilir (---)
        for line in lines[2:]:
            cols = self._split_preserve_inner_blanks(line)
            if len(cols) < num_cols:
                cols += ["&nbsp;"] * (num_cols - len(cols))
            elif len(cols) > num_cols:
                cols = cols[:num_cols]

            html += '<tr>'
            for c in cols:
                html += f'<td>{c if c != "" else "&nbsp;"}</td>'
            html += '</tr>\n'

        html += '</tbody>\n</table>'
        return html.strip()  # sonda newline bırakma

    # ---------- ANA DÖNÜŞTÜRÜCÜ ----------
    def transform_text_to_markdown(self, input_text: str) -> str:
        """
        Metni hafif HTML'e çevirir:
        - Markdown tablolarını <table> HTML'ine dönüştürür.
        - Hazır HTML <table> bloklarını korur.
        - Boş satırları sıkıştırır; tablo çevresindeki <br>'leri temizler.
        - 'pre-wrap' CSS'inde şişen boşlukları önlemek için çıplak newlineları kaldırır.
        """
        if not input_text:
            return ""

        # 1) Hazır HTML <table> bloklarını koru (place‑holder ile)
        html_tables: dict[str, str] = {}

        def _protect_html_table(m: re.Match) -> str:
            key = f"__HTML_TABLE__{len(html_tables)}__"
            html_tables[key] = m.group(0)
            return key

        protected = re.sub(r'(?is)(<table[\s\S]*?</table>)', _protect_html_table, input_text)

        # 2) Markdown tablo bloklarını yakala ve HTML'e çevir (place‑holder ile)
        md_tables: dict[str, str] = {}
        out_lines: list[str] = []
        lines = protected.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            if '|' in line and '<' not in line:
                j = i
                while j < len(lines) and '|' in lines[j] and '<' not in lines[j]:
                    j += 1
                block = '\n'.join(lines[i:j]).strip()
                bl = [ln for ln in block.split('\n') if ln.strip()]
                # 2. satır ayraç mı? (--- | :---: vb.)
                is_md_table = len(bl) >= 2 and re.match(r'^\s*[:\-| ]+\s*$', bl[1]) is not None
                if is_md_table:
                    key = f"__MD_TABLE__{len(md_tables)}__"
                    md_tables[key] = self.markdown_table_to_html(block).strip()
                    out_lines.append(key)
                    i = j
                    continue
            out_lines.append(line)
            i += 1

        protected = '\n'.join(out_lines)

        # 3) Satır satır işlem – boşluk yönetimi
        parts: list[str] = []
        last_was_table = False
        pending_blank = False

        for raw in protected.split('\n'):
            s = raw.strip()

            # a) Yer tutucular (tablolar) -> br ekleme, boşluk biriktirme yok
            if s in md_tables or s in html_tables:
                pending_blank = False  # tablo öncesi boşluğu düşür
                parts.append(md_tables.get(s, html_tables.get(s)))
                last_was_table = True
                continue

            # b) Boş satır -> sadece TEXT blokları arasında tek <br> iste
            if not s:
                if not last_was_table:  # tabloyla bitiyorsa boşluk biriktirme
                    pending_blank = True
                continue

            # c) Normal metin – biriktirilmiş boşluğu uygula
            if pending_blank:
                parts.append("<br>")
                pending_blank = False
            last_was_table = False

            # Temizlikler
            s = re.sub(r"(\d)''(\d)", r'\1"\2', s)
            s = s.replace("\\'", "'")
            for pat in ["\\(", "\\)", "\\\\,", "\\text", "\\frac"]:
                s = s.replace(pat, "")
            s = re.sub(r"【.*?】", "", s).strip()

            # **kalın**
            s = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", s)

            # Başlıklar
            m = re.match(r'^\s*(#{1,6})\s*(.*)$', s)
            if m:
                parts.append(f"<b>{m.group(2).strip()}</b><br>")
                continue

            # Listeler
            if s.startswith("- "):
                parts.append(f"&bull; {s[2:]}<br>")
                continue

            parts.append(f"{s}<br>")

        # ÖNEMLİ: çıplak '\n' bırakma
        result = ''.join(parts)

        # 4) Yer tutucuları geri koy
        for key, block in html_tables.items():
            result = result.replace(key, block.strip())
        for key, block in md_tables.items():
            result = result.replace(key, block.strip())

        # 5) Son temizlik: newlineları ve tablo çevresi <br>'leri sık
        result = re.sub(r'(?:\r?\n)+', '', result)        # kalan newlineları kaldır
        result = re.sub(r'>\s+<', '><', result)           # tag arası boşlukları sık
        result = re.sub(r'(<br>\s*){2,}', '<br>', result) # çoklu <br> -> tek
        result = re.sub(r'(<br>\s*)+(?=<table[^>]*>)', '', result)   # tablo öncesi <br> sil
        result = re.sub(r'(?<=</table>)(\s*<br>)+', '<br>', result)  # tablo sonrası en fazla 1 <br>

        return result
