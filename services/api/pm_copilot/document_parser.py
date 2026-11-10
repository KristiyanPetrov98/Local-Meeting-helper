"""Text extraction in a private subprocess. Never execute document content or render HTML."""
import csv
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import PurePosixPath

MAX_UPLOAD = 20*1024*1024
MAX_TEXT = 2_000_000
MAX_CHUNKS = 4000
PARSER_VERSION = 'm2-v1'
TEXT_EXTENSIONS = {'.txt','.md','.markdown','.py','.ts','.tsx','.js','.jsx','.cs','.java','.go','.rs','.sql',
                   '.json','.yaml','.yml','.xml','.graphql','.gql','.proto','.html','.css','.sh','.ini','.toml','.csv'}
ALLOWED = TEXT_EXTENSIONS | {'.pdf','.docx','.pptx','.xlsx'}


class ParseError(ValueError): pass


def validate_name(name):
    if not name or len(name)>180 or name in ('.','..') or any(c in name for c in ('/','\\',':')) or any(ord(c)<32 for c in name):
        raise ParseError('Use a plain filename, without paths or control characters')
    suffix = PurePosixPath(name).suffix.lower()
    if suffix not in ALLOWED: raise ParseError('Unsupported file extension')
    return suffix


def timestamp(value):
    if not value: return None
    if isinstance(value,datetime): dt=value
    else:
        text=str(value).strip().strip('"\'')
        if text.startswith('D:'):
            match=re.fullmatch(r"D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?(Z|[+-]\d{2}'?\d{2}'?)?",text)
            if not match: return None
            y,mo,d,h,mi,se,tz=match.groups()
            text=f'{y}-{mo or "01"}-{d or "01"}T{h or "00"}:{mi or "00"}:{se or "00"}'
            if tz and tz!='Z': text+=tz.replace("'",'')[:3]+':'+tz.replace("'",'')[3:]
            elif tz=='Z': text+='Z'
        try: dt=datetime.fromisoformat(text.replace('Z','+00:00'))
        except (ValueError,TypeError): return None
    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def validate_zip(data, marker):
    from defusedxml.ElementTree import fromstring
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos=archive.infolist()
            if len(infos)>10000 or sum(i.file_size for i in infos)>100*1024*1024:
                raise ParseError('Office archive exceeds extraction limits')
            if len(set(archive.namelist()))!=len(infos): raise ParseError('Duplicate Office archive parts are rejected')
            if marker not in archive.namelist(): raise ParseError('File content does not match its Office extension')
            for item in infos:
                if item.flag_bits & 1: raise ParseError('Encrypted Office archives are unsupported')
                if item.file_size>40*1024*1024 or item.file_size/max(1,item.compress_size)>200:
                    raise ParseError('Office archive exceeds compression limits')
                if 'vbaproject' in item.filename.lower(): raise ParseError('Macro-enabled document content is rejected')
                if item.filename.lower().endswith(('.xml','.rels')):
                    # Safe validation before handing parts to the Office parser; no external entities.
                    fromstring(archive.read(item),forbid_dtd=True,forbid_entities=True,forbid_external=True)
    except ParseError: raise
    except Exception as exc: raise ParseError('Invalid or unsafe Office archive') from exc


def _decoded(data):
    try: text=data.decode('utf-16' if data.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
    except UnicodeError as exc: raise ParseError('Text must use UTF-8 or BOM-marked UTF-16') from exc
    if '\x00' in text: raise ParseError('Binary content is not accepted as text')
    if len(text)>MAX_TEXT: raise ParseError('Extracted text exceeds two million characters')
    return text.replace('\r\n','\n').replace('\r','\n')


def parse_document(name, data):
    ext=validate_name(name)
    if not data or len(data)>MAX_UPLOAD: raise ParseError('Document must be between 1 byte and 20 MiB')
    units=[];modified=None;warnings=[];total=0
    def unit(text, locator):
        nonlocal total
        if not text.strip(): return
        if any(isinstance(v,str) and len(v)>500 for v in locator.values()): raise ParseError('Source heading or label exceeds 500 characters')
        total+=len(text)
        if total>MAX_TEXT or len(units)>=10000: raise ParseError('Extracted content exceeds indexing limits')
        units.append({'text':text,'locator':locator})
    try:
        if ext=='.pdf':
            from pypdf import PdfReader
            if not data.startswith(b'%PDF-'): raise ParseError('File is not a PDF')
            reader=PdfReader(io.BytesIO(data),strict=True)
            if reader.is_encrypted: raise ParseError('Encrypted PDFs are unsupported')
            if len(reader.pages)>2000: raise ParseError('PDF exceeds 2,000 pages')
            modified=timestamp((reader.metadata or {}).get('/ModDate'))
            for i,page in enumerate(reader.pages,1): unit(page.extract_text() or '',{'kind':'pdf','page':i})
        elif ext=='.docx':
            from docx import Document
            from docx.text.paragraph import Paragraph
            validate_zip(data,'word/document.xml')
            doc=Document(io.BytesIO(data));modified=timestamp(doc.core_properties.modified)
            headings=[];paragraph=0;table=0
            for block in doc.iter_inner_content():
                if isinstance(block,Paragraph):
                    paragraph+=1
                    match=re.match(r'Heading (\d)',block.style.name or '')
                    if match:
                        level=int(match[1]);headings=headings[:level-1]+[block.text]
                    unit(block.text,{'kind':'docx','paragraph':paragraph,'heading':' / '.join(headings)})
                else:
                    table+=1
                    for i,row in enumerate(block.rows,1):
                        unit('\t'.join(cell.text for cell in row.cells),{'kind':'docx_table','table':table,'row':i,'heading':' / '.join(headings)})
        elif ext=='.pptx':
            from pptx import Presentation
            validate_zip(data,'ppt/presentation.xml')
            deck=Presentation(io.BytesIO(data));modified=timestamp(deck.core_properties.modified)
            for slide_no,slide in enumerate(deck.slides,1):
                heading=slide.shapes.title.text if slide.shapes.title is not None else ''
                for shape_no,shape in enumerate(slide.shapes,1):
                    if shape.has_text_frame:
                        unit('\n'.join(p.text for p in shape.text_frame.paragraphs),{'kind':'pptx','slide':slide_no,'shape':shape_no,'heading':heading})
                    if shape.has_table:
                        for row_no,row in enumerate(shape.table.rows,1):
                            unit('\t'.join(c.text for c in row.cells),{'kind':'pptx_table','slide':slide_no,'shape':shape_no,'row':row_no,'heading':heading})
        elif ext=='.xlsx':
            from openpyxl import load_workbook
            from openpyxl.utils import get_column_letter
            validate_zip(data,'xl/workbook.xml')
            book=load_workbook(io.BytesIO(data),read_only=True,data_only=False,keep_links=False)
            try:
                modified=timestamp(book.properties.modified)
                for sheet in book:
                    if sheet.max_row and sheet.max_row>50000 or sheet.max_column and sheet.max_column>256:
                        raise ParseError('Worksheet exceeds 50,000 rows or 256 columns')
                    for row_no,row in enumerate(sheet.iter_rows(),1):
                        cells=[f'{get_column_letter(i)}{row_no}={c.value.isoformat() if isinstance(c.value,datetime) else c.value}' for i,c in enumerate(row,1) if c.value is not None]
                        if cells: unit(' | '.join(cells),{'kind':'xlsx','sheet':sheet.title,'range':f'A{row_no}:{get_column_letter(len(row))}{row_no}'})
                warnings.append('Spreadsheet formulas are indexed as source text; no formulas or external links are executed.')
            finally: book.close()
        else:
            text=_decoded(data)
            for line in text.splitlines()[:50]:
                match=re.match(r'^\s*(?:[\"\']?)(?:revision_date|last_updated|updated_at|modified_at|last_modified|x-revision-date|x-last-updated)(?:[\"\']?)\s*[:=]\s*(.+?)[,]?$',line,re.I)
                if match:
                    modified=timestamp(match[1].rstrip(','))
                    if modified: break
            if ext=='.json':
                value=json.loads(text,parse_constant=lambda v: (_ for _ in ()).throw(ParseError('Nonstandard JSON constant')))
                if isinstance(value,dict):
                    metadata=[value,value.get('info',{})]
                    for container in metadata:
                        if isinstance(container,dict):
                            for key in ['revision_date','last_updated','updated_at','modified_at','last_modified','x-revision-date','x-last-updated']:
                                candidate=timestamp(container.get(key))
                                if candidate: modified=candidate;break
            if ext in ('.yaml','.yml'):
                import yaml
                yaml.safe_load(text)  # SafeLoader never imports/executes document tags.
            if ext=='.xml':
                from defusedxml.ElementTree import fromstring
                fromstring(text,forbid_dtd=True,forbid_entities=True,forbid_external=True)
            if ext=='.csv':
                csv.field_size_limit(100000)
                try: dialect=csv.Sniffer().sniff(text[:4096],delimiters=',;\t|')
                except csv.Error: dialect=csv.excel
                reader=csv.reader(io.StringIO(text),dialect);last_line=0
                for row_no,row in enumerate(reader,1):
                    if len(row)>256: raise ParseError('CSV exceeds 256 columns')
                    unit('\t'.join(row),{'kind':'csv','row':row_no,'line_start':last_line+1,'line_end':reader.line_num})
                    last_line=reader.line_num
            else:
                headings=[];buffer=[];first=1;endpoint=None
                def finish(end):
                    if buffer:
                        locator={'kind':'text','line_start':first,'line_end':end,'heading':' / '.join(headings)}
                        if endpoint: locator['endpoint']=endpoint
                        unit(''.join(buffer),locator)
                lines=text.splitlines(keepends=True)
                for number,line in enumerate(lines,1):
                    heading=re.match(r'^(#{1,6})\s+(.+)',line) if ext in ('.md','.markdown') else None
                    symbol=re.match(r'^\s*(?:(?:async\s+)?def|class|function|func|fn|type|message|service|CREATE\s+TABLE)\s+([\w.]+)',line,re.I) if ext not in ('.md','.markdown','.txt') else None
                    path=re.match(r'^\s{0,6}(/[^\s:]*):\s*$',line) if ext in ('.yaml','.yml') else None
                    method=re.match(r'^\s+(get|post|put|patch|delete|head|options):',line,re.I) if ext in ('.yaml','.yml') else None
                    boundary=heading or symbol or path or method or sum(map(len,buffer))>=900
                    if boundary:
                        finish(number-1);buffer=[];first=number
                        if heading: headings=headings[:len(heading[1])-1]+[heading[2].strip()]
                        if symbol: headings=[symbol[1]]
                        if path: endpoint=path[1]
                        if method and endpoint: endpoint=method[1].upper()+' '+endpoint.split(' ')[-1]
                    buffer.append(line)
                finish(len(lines))
    except ParseError: raise
    except ImportError as exc: raise ParseError('Install the document parser dependencies first') from exc
    except Exception as exc: raise ParseError('Document could not be safely parsed') from exc
    if not units: raise ParseError('No searchable text found. Scanned documents require Phase 2 OCR.')
    chunks=[]
    for unit_no,entry in enumerate(units):
        text=entry['text'];start=0
        while start<len(text):
            end=min(len(text),start+1100)
            if end<len(text):
                split=text.rfind('\n',start+200,end)
                if split>=0: end=split+1
            value=text[start:end]
            if value.strip():
                locator={**entry['locator'],'unit':unit_no,'char_start':start,'char_end':end}
                if locator['kind']=='text':
                    locator['line_start']=entry['locator']['line_start']+text[:start].count('\n')
                    locator['line_end']=locator['line_start']+value.rstrip('\n').count('\n')
                chunks.append({'text':value,'locator':locator,'text_hash':hashlib.sha256(value.encode()).hexdigest()})
                if len(chunks)>MAX_CHUNKS: raise ParseError('Document exceeds 4,000 searchable chunks')
            start=end
    return {'units':units,'chunks':chunks,'internal_modified_at':modified,'warnings':warnings,'parser_version':PARSER_VERSION}
