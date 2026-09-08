"""Create a versioned inquiry master without modifying the original."""
from pathlib import Path
import pymupdf as fitz

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / 'templates/CHUCHU_AI_STUDIO_Client_Project_Inquiry_Form.pdf'
UPDATED = ROOT / 'templates/CHUCHU_AI_STUDIO_Client_Project_Inquiry_Form_With_Address.pdf'

def add_address(doc):
    page = doc[0]
    if any(w.field_name == 'client_address' for p in doc for w in p.widgets() or []):
        raise ValueError('Address field already exists')
    page.insert_text((42.5197, 224.5), 'Registered / Billing Address (for agreement)',
                     fontname='hebo', fontsize=7.7, color=(107/255, 113/255, 128/255))
    w = fitz.Widget()
    w.field_name = 'client_address'
    w.field_label = 'Registered / Billing Address (for agreement)'
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.rect = fitz.Rect(42.5197, 227, 552.7559, 242.5)
    w.text_font = 'Helv'
    w.text_fontsize = 8
    w.text_color = (0.13, 0.17, 0.20)
    w.border_color = (0.82, 0.86, 0.91)
    w.border_width = 0.6
    w.fill_color = (1, 1, 1)
    page.add_widget(w)

if __name__ == '__main__':
    if UPDATED.exists():
        raise SystemExit('Refusing to overwrite existing updated master')
    with fitz.open(ORIGINAL) as doc:
        add_address(doc)
        doc.save(UPDATED, deflate=True)
    print(UPDATED)
