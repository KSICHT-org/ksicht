import os
import io
from pathlib import Path
from typing import List, Optional, Sequence

from django.conf import settings
from pdfrw import PdfReader, PdfWriter, PdfDict
from pypdf import PdfReader as PdfFileReader, PageObject
from pypdf import PdfWriter as PdfFileWriter
from pypdf.errors import PdfReadError
import reportlab
from pypdf import PaperSize
from reportlab.lib.pagesizes import A4, C3, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from typing_extensions import TypedDict


__all__ = (
    "envelopes",
    "concatenate",
    "PdfReadError",
)

reportlab.rl_config.TTFSearchPath.append(str(settings.BASE_DIR) + "/fonts")
pdfmetrics.registerFont(TTFont("Helvetica", "Helvetica.ttf"))


class EnvelopeRecipientInfo(TypedDict):
    lines: Sequence[str]
    note: Optional[str]


def envelopes(recipients: List[EnvelopeRecipientInfo], our_lines, out_file):
    """Generate envelopes with address block."""
    pagesize = landscape(C3)
    page_width, page_height = pagesize

    ksicht_contact_paragraph_style = ParagraphStyle(
        "Normal",
        fontName="Helvetica",
        fontSize=28,
        leading=32,
    )
    note_paragraph_style = ParagraphStyle(
        "Normal",
        fontName="Helvetica",
        alignment=reportlab.lib.enums.TA_RIGHT,
        fontSize=28,
        leading=32,
    )
    page_paragraph_style = ParagraphStyle(
        "Normal",
        fontName="Helvetica",
        fontSize=38,
        leading=56,
        borderWidth=1,
        borderRadius=8,
        borderPadding=24,
        borderColor="#000",
    )
    ksicht_contact_paragraph = Paragraph(
        "<br />".join(our_lines), style=ksicht_contact_paragraph_style
    )
    ksicht_contact_height = ksicht_contact_paragraph.wrap(620, 1000)[1]

    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=pagesize)

    for recipient in recipients:
        paragraph = Paragraph(
            "<br />".join(recipient["lines"]), style=page_paragraph_style
        )
        paragraph_width = paragraph.wrap(700, 1000)[0]
        paragraph.drawOn(can, page_width - paragraph_width - 48, 270)

        ksicht_contact_paragraph.drawOn(
            can, 24, page_height - 24 - ksicht_contact_height
        )

        if recipient["note"]:
            note_paragraph = Paragraph(
                recipient["note"],
                style=note_paragraph_style,
            )
            note_width, note_height = note_paragraph.wrap(300, 200)
            note_paragraph.drawOn(
                can, page_width - 24 - note_width, page_height - 24 - note_height
            )

        can.showPage()  # Close current page & start new one

    can.save()
    packet.seek(0)
    out_file.write(packet.read())

    return out_file


def concatenate(in_files, out_file, as_duplex=False):
    """Merge all input PDF files into a single out file."""
    writer = PdfWriter()

    for f in in_files:
        current_pdf = PdfReader(f)
        num_pages = len(current_pdf.pages)

        writer.addpages(current_pdf.pages)

        if as_duplex and (num_pages >= 1) and (num_pages % 2 == 1):
            # add blank A4 page
            writer.addpage(get_blank_page())

    writer.write(out_file)
    return out_file


def get_blank_page():
    if not Path(blank_pdf_filename := settings.BLANK_PDF_FILEPATH).exists():
        writer = PdfFileWriter()
        writer.add_blank_page(width=PaperSize.A4.width, height=PaperSize.A4.height)
        with open(blank_pdf_filename, "wb") as fp:
            writer.write(fp)
            writer.close()
    return PdfReader(blank_pdf_filename).pages[0]


def delete_blank_file():
    if Path(blank_pdf_filename := settings.BLANK_PDF_FILEPATH).exists():
        os.remove(blank_pdf_filename)


def page_with_memo(x: int, y: int, label: str):
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)
    can.setFont("Helvetica", 24)
    can.drawString(x, y, label)
    can.save()
    packet.seek(0)
    return PdfFileReader(packet).pages[0]


def prepare_submission_for_export(in_file, label: str):
    """Prepare submission for exporting later on."""
    out_pdf = PdfFileWriter()

    # Make sure the PDF file is valid. If it isn't render a PDF with error message contained.
    try:
        in_file.seek(0)
        in_memory_pdf = io.BytesIO(in_file.read())
        in_pdf = PdfFileReader(in_memory_pdf)
        out_pdf.append_pages_from_reader(in_pdf)
    except Exception:
        out_pdf.add_page(page_with_memo(10, 200, "!! Tento PDF soubor je poškozený !!"))

    # Write person label on every page
    working_file = io.BytesIO()
    out_pdf.write(working_file)
    working_file.seek(0)

    in_pdf = PdfFileReader(working_file)
    memo_page = page_with_memo(10, 10, label)

    out_normal = PdfFileWriter()
    for page in in_pdf.pages:
        page.merge_page(memo_page)
        out_normal.add_page(page)

    # Write normal version to buffer, then create duplex from it
    normal_buf = io.BytesIO()
    out_normal.write(normal_buf)
    normal_buf.seek(0)

    # Build duplex version by reading from normal and optionally adding blank page
    out_duplex = PdfFileWriter()
    duplex_reader = PdfFileReader(normal_buf)
    out_duplex.append_pages_from_reader(duplex_reader)

    num_pages = len(duplex_reader.pages)
    if (num_pages % 2 == 1) and num_pages > 1:
        out_duplex.add_blank_page(width=PaperSize.A4.width, height=PaperSize.A4.height)

    return out_normal, out_duplex
