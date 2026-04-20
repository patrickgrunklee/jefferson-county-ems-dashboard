"""Convert the IE Visual Tools markdown to a self-contained HTML with embedded images."""
import base64, os, re

ROOT = os.path.dirname(__file__)
md_path = os.path.join(ROOT, "IE_Visual_Tools_Jefferson_County_EMS.md")

with open(md_path, "r", encoding="utf-8") as f:
    md = f.read()

# Collect all image references and convert to base64
def embed_image(match):
    alt = match.group(1)
    rel_path = match.group(2)
    abs_path = os.path.join(ROOT, rel_path.replace("/", os.sep))
    if os.path.exists(abs_path):
        with open(abs_path, "rb") as img:
            b64 = base64.b64encode(img.read()).decode()
        return f'<img src="data:image/png;base64,{b64}" alt="{alt}" style="max-width:100%; border:1px solid #e5e7eb; border-radius:8px; margin:16px 0;">'
    return match.group(0)

md = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', embed_image, md)

# Simple markdown to HTML conversion
import html as html_mod

def md_to_html(text):
    lines = text.split('\n')
    out = []
    in_table = False
    in_code = False

    for line in lines:
        stripped = line.strip()

        # Code blocks
        if stripped.startswith('```'):
            in_code = not in_code
            continue
        if in_code:
            out.append(f'<pre><code>{html_mod.escape(line)}</code></pre>')
            continue

        # Headings
        if stripped.startswith('# ') and not stripped.startswith('## '):
            content = stripped[2:]
            out.append(f'<h1>{content}</h1>')
            continue
        if stripped.startswith('## ') and not stripped.startswith('### '):
            content = stripped[3:]
            anchor = content.lower().replace(' ', '-').replace('/', '-').replace('&', '').replace('.', '')
            out.append(f'<h2 id="{anchor}">{content}</h2>')
            continue
        if stripped.startswith('### '):
            content = stripped[4:]
            anchor = content.lower().replace(' ', '-').replace('/', '-').replace('&', '').replace('.', '').replace('(', '').replace(')', '')
            out.append(f'<h3 id="{anchor}">{content}</h3>')
            continue

        # Horizontal rule
        if stripped == '---':
            out.append('<hr>')
            continue

        # Table rows
        if '|' in stripped and stripped.startswith('|'):
            cells = [c.strip() for c in stripped.split('|')[1:-1]]
            if all(set(c) <= set('- :') for c in cells):
                continue  # skip separator row
            if not in_table:
                out.append('<table>')
                in_table = True
                out.append('<tr>' + ''.join(f'<th>{format_inline(c)}</th>' for c in cells) + '</tr>')
            else:
                out.append('<tr>' + ''.join(f'<td>{format_inline(c)}</td>' for c in cells) + '</tr>')
            continue
        else:
            if in_table:
                out.append('</table>')
                in_table = False

        # Already-converted img tags
        if '<img ' in stripped:
            out.append(line)
            continue

        # Ordered list
        m = re.match(r'^(\d+)\.\s+(.+)', stripped)
        if m:
            out.append(f'<p style="margin:2px 0 2px 20px;">{m.group(1)}. {format_inline(m.group(2))}</p>')
            continue

        # Unordered list
        if stripped.startswith('- '):
            out.append(f'<li>{format_inline(stripped[2:])}</li>')
            continue

        # Empty line
        if not stripped:
            out.append('<br>')
            continue

        # Paragraph
        out.append(f'<p>{format_inline(stripped)}</p>')

    if in_table:
        out.append('</table>')

    return '\n'.join(out)

def format_inline(text):
    # Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Italic with *
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    # Links
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    return text

body = md_to_html(md)

html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IE Visual Tools - Jefferson County EMS</title>
<style>
  body {{
    font-family: 'Segoe UI', -apple-system, sans-serif;
    max-width: 1100px;
    margin: 0 auto;
    padding: 40px 30px;
    background: #fafafa;
    color: #1e293b;
    line-height: 1.6;
  }}
  h1 {{
    font-size: 2em;
    border-bottom: 3px solid #2563eb;
    padding-bottom: 10px;
    color: #1e293b;
  }}
  h2 {{
    font-size: 1.5em;
    color: #2563eb;
    margin-top: 40px;
    border-bottom: 1px solid #e5e7eb;
    padding-bottom: 6px;
  }}
  h3 {{
    font-size: 1.25em;
    color: #374151;
    margin-top: 30px;
  }}
  hr {{
    border: none;
    border-top: 1px solid #e5e7eb;
    margin: 30px 0;
  }}
  table {{
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0;
    font-size: 0.9em;
  }}
  th {{
    background: #2563eb;
    color: white;
    padding: 10px 12px;
    text-align: left;
    font-weight: 600;
  }}
  td {{
    padding: 8px 12px;
    border-bottom: 1px solid #e5e7eb;
  }}
  tr:nth-child(even) td {{
    background: #f8fafc;
  }}
  img {{
    max-width: 100%;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    margin: 16px 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  }}
  em {{
    color: #6b7280;
  }}
  p {{
    margin: 8px 0;
  }}
  a {{
    color: #2563eb;
    text-decoration: none;
  }}
  a:hover {{
    text-decoration: underline;
  }}
  li {{
    margin: 4px 0 4px 20px;
  }}
  @media print {{
    body {{ max-width: 100%; padding: 20px; }}
    img {{ page-break-inside: avoid; max-width: 95%; }}
    h2, h3 {{ page-break-after: avoid; }}
  }}
</style>
</head>
<body>
{body}
</body>
</html>
"""

out_path = os.path.join(ROOT, "IE_Visual_Tools_Jefferson_County_EMS.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(html_content)
print(f"HTML saved: {out_path}")
