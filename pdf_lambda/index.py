import os
import json
import logging
import boto3
import re
from io import BytesIO
from datetime import date

logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

s3 = boto3.client('s3')

def handler(event, context):
    """Generate professional PDF appeal letter using reportlab."""
    bucket = os.environ['DATA_BUCKET']
    claim_id = event.get('claimId', '')
    appeal_text = event.get('appealText', '') or event.get('agentResponse', '')
    claim_details = event.get('claimDetails', {}) or {}
    parsed_entities = event.get('parsedEntities', {}) or {}
    analysis_data = event.get('analysisJson', '') or event.get('analysis', '')

    if isinstance(analysis_data, str) and analysis_data:
        try:
            analysis_data = json.loads(analysis_data)
        except:
            analysis_data = {}
    elif not isinstance(analysis_data, dict):
        analysis_data = {}

    if not claim_id:
        return {'statusCode': 400, 'body': 'Missing claimId'}
    if not appeal_text:
        return {'statusCode': 400, 'body': 'Missing appeal text', 'claimId': claim_id}

    try:
        pdf_bytes = generate_pdf(claim_id, appeal_text, claim_details, parsed_entities, analysis_data)
        
        pdf_key = f'appeals/{claim_id}/appeal_letter.pdf'
        s3.put_object(
            Bucket=bucket,
            Key=pdf_key,
            Body=pdf_bytes,
            ContentType='application/pdf',
            ServerSideEncryption='AES256'
        )
        
        logger.info(f"PDF generated: s3://{bucket}/{pdf_key}")
        return {
            'statusCode': 200,
            'claimId': claim_id,
            'pdfKey': pdf_key,
            'bucket': bucket
        }
    except Exception as e:
        logger.error(f"Error generating PDF: {e}")
        # Fallback: save as text
        txt_key = f'appeals/{claim_id}/appeal_letter.txt'
        s3.put_object(
            Bucket=bucket,
            Key=txt_key,
            Body=appeal_text.encode('utf-8'),
            ContentType='text/plain',
            ServerSideEncryption='AES256'
        )
        return {
            'statusCode': 200,
            'claimId': claim_id,
            'pdfKey': txt_key,
            'bucket': bucket,
            'message': 'Saved as text (PDF generation failed)'
        }


def generate_pdf(claim_id, appeal_text, claim_details, parsed_entities, analysis_data):
    """Generate a professional PDF using reportlab."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib import colors

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        leftMargin=0.75*inch, rightMargin=0.75*inch,
        topMargin=0.75*inch, bottomMargin=0.75*inch
    )

    styles = getSampleStyleSheet()
    
    # Custom styles
    styles.add(ParagraphStyle(
        name='AppealTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=HexColor('#1a365d'),
        spaceAfter=12,
        alignment=TA_CENTER
    ))
    styles.add(ParagraphStyle(
        name='SectionHeader',
        parent=styles['Heading2'],
        fontSize=11,
        textColor=HexColor('#2c5282'),
        spaceBefore=16,
        spaceAfter=8,
        borderWidth=0,
        leftIndent=0
    ))
    styles.add(ParagraphStyle(
        name='BodyText2',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        spaceAfter=6
    ))
    styles.add(ParagraphStyle(
        name='BulletText',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        leftIndent=20,
        spaceAfter=4
    ))

    elements = []
    
    # Title
    elements.append(Paragraph("FORMAL APPEAL OF CLAIM DENIAL", styles['AppealTitle']))
    elements.append(HRFlowable(width="100%", thickness=2, color=HexColor('#2c5282')))
    elements.append(Spacer(1, 12))

    # Clean the appeal text
    clean_text = clean_appeal_text(appeal_text)
    
    # Parse and render the appeal text
    lines = clean_text.split('\n')
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            elements.append(Spacer(1, 6))
            continue
        
        # Detect section headers (ALL CAPS or Title Case ending with colon)
        is_header = False
        if stripped.isupper() and len(stripped) > 3 and len(stripped) < 80 and not stripped[0].isdigit():
            is_header = True
        elif stripped.endswith(':') and len(stripped) < 60 and not stripped.startswith('-'):
            words = stripped.rstrip(':').split()
            if len(words) <= 8 and sum(1 for w in words if w[0:1].isupper()) >= len(words) * 0.5:
                is_header = True
        
        if is_header:
            display = stripped.rstrip(':')
            if display.isupper():
                display = display.title()
            elements.append(Spacer(1, 8))
            elements.append(HRFlowable(width="100%", thickness=0.5, color=HexColor('#e2e8f0')))
            elements.append(Paragraph(f"<b>{escape_html(display)}</b>", styles['SectionHeader']))
        elif stripped.startswith('- ') or stripped.startswith('* ') or stripped.startswith('\u2022'):
            body = re.sub(r'^[-*\u2022\u2023\u25E6]\s*', '', stripped)
            elements.append(Paragraph(f"\u2022  {escape_html(body)}", styles['BulletText']))
        elif re.match(r'^\d+\.\s', stripped):
            elements.append(Paragraph(escape_html(stripped), styles['BulletText']))
        else:
            # Check if it's a key:value pair (like "Patient Name: John Smith")
            if ':' in stripped and len(stripped.split(':')[0]) < 30:
                key, _, val = stripped.partition(':')
                if val.strip():
                    elements.append(Paragraph(f"<b>{escape_html(key)}:</b> {escape_html(val.strip())}", styles['BodyText2']))
                else:
                    elements.append(Paragraph(escape_html(stripped), styles['BodyText2']))
            else:
                elements.append(Paragraph(escape_html(stripped), styles['BodyText2']))

    # Build PDF
    doc.build(elements)
    return buffer.getvalue()


def clean_appeal_text(text):
    """Clean markdown and Unicode from appeal text."""
    # Remove markdown
    text = re.sub(r'```[a-z]*\n?', '', text)
    text = re.sub(r'```', '', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'^\s*#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^---+\s*$', '', text, flags=re.MULTILINE)
    
    # Replace Unicode chars
    text = text.replace('\u2014', '-').replace('\u2013', '-')
    text = text.replace('\u2018', "'").replace('\u2019', "'")
    text = text.replace('\u201c', '"').replace('\u201d', '"')
    text = text.replace('\u2026', '...')
    
    # Remove "Enclosed Documentation" sections
    text = re.sub(r'(?i)(ENCLOSED DOCUMENTATION|SUPPORTING DOCUMENTATION ENCLOSED|ATTACHMENTS|ENCLOSURES)[:\s]*\n([\s\S]*?)(?=\n[A-Z]{2,}|\n(?:Sincerely|REQUEST|SUBMISSION|FINANCIAL|CLOSING)|$)', '', text)
    
    # Remove leading "Appeal Letter" header
    lines = text.split('\n')
    while lines and lines[0].strip().lower().replace('*', '').replace('#', '').strip() in ('appeal letter', 'appeal letter:', ''):
        lines.pop(0)
    
    return '\n'.join(lines)


def escape_html(text):
    """Escape HTML special chars for reportlab Paragraph."""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
