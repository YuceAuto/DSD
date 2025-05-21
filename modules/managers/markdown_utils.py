import re

class MarkdownProcessor:
    def transform_text_to_markdown(self, input_text):
        """
        Kullanıcıya gösterilecek metni satır satır işleyerek:
          - Başında # (1-6 adet) ister boşluklu ister boşluksuz olsun -> <b>Başlık</b> dönüştürür.
          - **kalın** ifadeleri <b>...</b> ile değiştirir.
          - Kalan satırları <br> ekleyerek HTML döndürür.
        """
        lines = input_text.split('\n')
        transformed_lines = []

        for line in lines:
            stripped_line = line.strip()

            # Örnek düzeltmeler
            stripped_line = re.sub(r"(\d)''(\d)", r'\1"\2', stripped_line)
            stripped_line = stripped_line.replace("\\'", "'")

            # **kalın** -> <b>...</b>
            stripped_line = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", stripped_line)

            # Örnek: PDF referanslarını temizleme
            stripped_line = re.sub(r"【.*?】", "", stripped_line).strip()

            # Başında 1-6 adet '#' -> heading
            heading_match = re.match(r'^(#{1,6})(\s*)(.*)$', stripped_line)
            if heading_match:
                heading_text = heading_match.group(3)
                transformed_lines.append(f"<b>{heading_text}</b><br>")
                continue

            # Liste satırları ("- " ile başlıyorsa)
            if stripped_line.startswith('- '):
                transformed_lines.append(f"&bull; {stripped_line[2:]}<br>")
            else:
                transformed_lines.append(f"{stripped_line}<br>")

        return ''.join(transformed_lines)

    def extract_markdown_tables_from_text(self, text):
        lines = text.splitlines()
        tables = []
        current_table = []
        for line in lines:
            if '|' in line.strip():
                current_table.append(line)
            else:
                if current_table:
                    tables.append('\n'.join(current_table))
                    current_table = []
        if current_table:
            tables.append('\n'.join(current_table))
        return tables

    def fix_table_characters(self, table_markdown: str) -> str:
        fixed_lines = []
        lines = table_markdown.split('\n')
        for line in lines:
            if '|' not in line:
                fixed_lines.append(line)
                continue
            columns = line.split('|')
            fixed_columns = []
            for col in columns:
                col = col.strip()
                col = col.replace('**', '')
                col = re.sub(r'(\d)\'\'(\d)', r'\1/\2', col)
                col = re.sub(r'([A-Za-z])//([A-Za-z])', r"\1'\2", col)
                fixed_columns.append(col)
            fixed_line = ' | '.join(fixed_columns)
            fixed_lines.append(fixed_line)
        return '\n'.join(fixed_lines)

    def markdown_table_to_html(self, md_table_str):
        md_table_str = self.fix_table_characters(md_table_str)
        lines = md_table_str.strip().split("\n")
        if len(lines) < 2:
            return f"<p>{md_table_str}</p>"

        header_cols = [col.strip() for col in lines[0].split("|") if col.strip()]
        body_lines = lines[2:]

        html = '<table class="table table-bordered table-sm my-blue-table">\n'
        html += '<thead><tr>'
        for col in header_cols:
            html += f'<th>{col}</th>'
        html += '</tr></thead>\n<tbody>\n'

        for line in body_lines:
            row = line.strip()
            if not row:
                continue
            cols = [c.strip() for c in row.split("|") if c.strip()]
            html += '<tr>'
            for c in cols:
                html += f'<td>{c}</td>'
            html += '</tr>\n'
        html += '</tbody>\n</table>'
        return html