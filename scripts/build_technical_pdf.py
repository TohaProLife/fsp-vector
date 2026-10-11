"""Build the submission manual from its editable Markdown source."""
from pathlib import Path
import re
from xml.sax.saxutils import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether

ROOT = Path(__file__).resolve().parents[1]


def inline_markdown(value):
    """Render our small manual's inline syntax without raw Markdown markers."""
    parts = []
    pattern = r'\[([^\]]+)\]\(([^)]+)\)|`([^`]+)`|\*\*([^*]+)\*\*'
    prior = 0
    for match in re.finditer(pattern, value):
        parts.append(escape(value[prior:match.start()]))
        label, target, code, bold = match.groups()
        if label is not None:
            label = escape(label)
            if target.startswith(('https://', 'http://')):
                parts.append(f'<link href="{escape(target, {chr(34): "&quot;"})}" color="#565bc4">{label}</link>')
            else:
                parts.append(f'{label} <font size="8" color="#586577">({escape(target)})</font>')
        elif code is not None:
            parts.append(f'<font color="#43506a">{escape(code)}</font>')
        else:
            parts.append(f'<b>{escape(bold)}</b>')
        prior = match.end()
    parts.append(escape(value[prior:]))
    return ''.join(parts).replace('\n', '<br/>')


def main():
    pdfmetrics.registerFont(TTFont('Golos', str(ROOT / 'apps/web/public/fonts/golos.ttf')))
    pdfmetrics.registerFontFamily('Golos', normal='Golos', bold='Golos', italic='Golos', boldItalic='Golos')
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('BodyRU', fontName='Golos', fontSize=10, leading=15, spaceAfter=9,
                              alignment=TA_LEFT, textColor=HexColor('#202c3c'), splitLongWords=True))
    styles.add(ParagraphStyle('TitleRU', parent=styles['BodyRU'], fontSize=25, leading=32, spaceAfter=18))
    styles.add(ParagraphStyle('HeadingRU', parent=styles['BodyRU'], fontSize=15, leading=21,
                              spaceBefore=17, spaceAfter=10, keepWithNext=True))
    def footer(canvas, document):
        canvas.setFont('Golos', 8)
        canvas.setFillColor(HexColor('#68768a'))
        canvas.drawString(44, 29, 'ФСП Вектор | Техническое руководство | Локальный прототип')
        canvas.drawRightString(A4[0] - 44, 29, str(document.page))
    story = []
    for block in (ROOT / 'docs/submission/technical-guide.md').read_text('utf-8').split('\n\n'):
        block = block.strip().replace('\u2011', '-').replace('\u2013', '-').replace('\u2014', '-')
        if not block: continue
        if block.startswith('#'):
            first, _, remainder = block.partition('\n')
            blocks = [first, remainder] if remainder else [first]
        else:
            blocks = block.splitlines() if re.match(r'^\d+\.', block) else [block]
        for line in blocks:
            style = 'TitleRU' if line.startswith('# ') else 'HeadingRU' if line.startswith('## ') else 'BodyRU'
            text = inline_markdown(re.sub(r'^#{1,2} ', '', line))
            story.append(Paragraph(text, styles[style]))
    output = ROOT / 'output/pdf/fsp-vector-technical-guide.pdf'
    output.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(output), pagesize=A4, leftMargin=44, rightMargin=44, topMargin=43,
                      bottomMargin=48, title='ФСП Вектор - техническое руководство', author='Команда ФСП Вектор')\
        .build(story, onFirstPage=footer, onLaterPages=footer)
    print(str(output))


if __name__ == '__main__':
    main()
