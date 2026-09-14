"""Read a plain test-case sheet (ID, title, preconditions, steps, test data, expected result).

The file carries no rules and no rule references. This parser only finds the sheet, the header
row and the columns, keeps every original cell with its coordinate, and suggests a column mapping
from the header wording; the person importing confirms the mapping before anything is interpreted.
"""
import csv,io
from datetime import date,datetime
from decimal import Decimal
from pathlib import Path
from factory.models.test_suite import COLUMNS
from factory.services.text_patterns import fold,normalize
from .common import ImportFailure,ImportIssue,document,MAX_ROWS

MEDIA={".xlsx":"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",".csv":"text/csv"}
PREVIEW_ROWS=8
# Folded header wording, longest match wins, so "test case id" beats "id" and "expected result" beats "result".
HINTS={
    "test_id":("test case id","testcase id","test id","tc id","case id","ma test","ma tc","ma testcase","id"),
    "title":("test case name","test name","test case title","title","ten test","ten testcase","ten","tieu de","scenario","summary","kich ban"),
    "preconditions":("precondition","pre-condition","pre condition","dieu kien tien quyet","dieu kien","tien de","given"),
    "steps":("test steps","steps","step","cac buoc","buoc thuc hien","thao tac","action","procedure","when"),
    "test_data":("test data","du lieu test","du lieu kiem thu","du lieu","input data","inputs","input","dau vao","tham so","parameter","data"),
    "expected":("expected result","expected results","expected outcome","expected","ket qua mong doi","ket qua ky vong","ket qua","mong doi","then","output"),
}

def column_letter(index):
    """1-based column index to A, B, ... AA."""
    letters=""
    while index>0:
        index,remainder=divmod(index-1,26);letters=chr(65+remainder)+letters
    return letters

def cell_text(value):
    if value is None:return ""
    if isinstance(value,bool):return "TRUE" if value else "FALSE"
    if isinstance(value,float):
        return str(int(value)) if value.is_integer() else format(Decimal(repr(value)).normalize(),"f")
    if isinstance(value,datetime):return value.date().isoformat() if value.time()==datetime.min.time() else value.isoformat(sep=" ")
    if isinstance(value,date):return value.isoformat()
    return normalize(value).strip()

def suggest_mapping(headers):
    """headers: list of (letter, text). Each canonical column takes the best-scoring header once."""
    scores=[]
    for letter,text in headers:
        folded=fold(text).strip()
        if not folded:continue
        for column,hints in HINTS.items():
            for hint in hints:
                if folded==hint:scores.append((3,len(hint),column,letter));break
                if hint in folded:scores.append((1,len(hint),column,letter));break
    mapping={};taken=set()
    for _,_,column,letter in sorted(scores,key=lambda s:(-s[0],-s[1])):
        if column in mapping or letter in taken:continue
        mapping[column]=letter;taken.add(letter)
    return mapping

def detect_header_row(grid):
    """First row within the top ten that has at least two filled cells and one recognisable header."""
    for number,row in enumerate(grid[:10],1):
        filled=[text for text in row if text]
        if len(filled)>=2 and suggest_mapping([(column_letter(i),t) for i,t in enumerate(row,1)]):return number
    return 1

def read_grid(data,name):
    """Every sheet as (name, rows of text). Formula cells contribute their last calculated value."""
    suffix=Path(name).suffix.lower()
    if suffix not in MEDIA:raise ImportFailure((ImportIssue(name,"Supported test-case files: .xlsx, .csv"),))
    if suffix==".csv":
        try:text=data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:raise ImportFailure((ImportIssue(name,"CSV must be UTF-8 text"),)) from exc
        sample=text[:4096]
        try:dialect=csv.Sniffer().sniff(sample,delimiters=",;\t")
        except csv.Error:dialect=csv.excel
        rows=[[cell_text(value) for value in row] for row in csv.reader(io.StringIO(text),dialect)]
        # Preserve empty records: source cell coordinates must match the original file.
        if len(rows)>MAX_ROWS+1 or any(len(row)>64 for row in rows):raise ImportFailure((ImportIssue(name,"Sheet exceeds 5000 data rows or 64 columns",sheet="CSV"),))
        return [("CSV",rows)]
    from .excel_parser import open_workbook
    workbook=open_workbook(data,name,data_only=True)
    try:
        sheets=[]
        for sheet in workbook.worksheets:
            if sheet.max_row>MAX_ROWS+1 or sheet.max_column>64:
                raise ImportFailure((ImportIssue(name,"Sheet exceeds 5000 data rows or 64 columns",sheet=sheet.title),))
            rows=[]
            for row in sheet.iter_rows(min_row=1,max_row=sheet.max_row,max_col=sheet.max_column,values_only=True):
                rows.append([cell_text(value) for value in row])
            while rows and not any(rows[-1]):rows.pop()
            sheets.append((sheet.title,rows))
        return sheets
    finally:workbook.close()

def inspect(data,name):
    """Sheets, detected header rows, previews and a suggested mapping, so the person can confirm."""
    sheets=read_grid(data,name)
    doc=document(data,name,MEDIA[Path(name).suffix.lower()])
    result=[]
    for title,grid in sheets:
        if not grid or not any(any(row) for row in grid):continue
        header_row=detect_header_row(grid)
        width=max(len(row) for row in grid)
        headers=[(column_letter(i),grid[header_row-1][i-1] if i-1<len(grid[header_row-1]) else "") for i in range(1,width+1)]
        preview=[[row[i-1] if i-1<len(row) else "" for i in range(1,width+1)] for row in grid[header_row:header_row+PREVIEW_ROWS]]
        result.append(dict(name=title,header_row=header_row,headers=[dict(letter=l,text=t) for l,t in headers],preview=preview,
            rows=sum(1 for row in grid[header_row:] if any(row)),suggested=suggest_mapping(headers)))
    if not result:raise ImportFailure((ImportIssue(name,"The file has no sheet with data"),))
    return dict(filename=name,document=doc.to_dict(),sheets=result)

def validate_mapping(mapping,headers):
    letters={h[0] for h in headers}
    if type(mapping) is not dict or not mapping or not set(mapping)<=set(COLUMNS):raise ValueError("Mapping keys must be test-case columns")
    if not all(type(v) is str and v in letters for v in mapping.values()):raise ValueError("Mapping values must be column letters of the chosen sheet")
    if len(set(mapping.values()))!=len(mapping):raise ValueError("One sheet column cannot feed two fields")
    if "expected" not in mapping:raise ValueError("Map the expected-result column")
    if not any(key in mapping for key in ("test_data","title","steps")):raise ValueError("Map at least the test-data column (or a title/steps column to read inputs from)")
    return mapping

def extract_rows(data,name,sheet,mapping,header_row=None):
    """Located cells for every data row of the chosen sheet, honouring the confirmed mapping."""
    grids=dict(read_grid(data,name))
    if sheet not in grids:raise ValueError("Sheet not found: "+sheet)
    grid=grids[sheet]
    header_row=header_row or detect_header_row(grid)
    if not 1<=header_row<=len(grid):raise ValueError("Header row outside the sheet")
    width=max(len(row) for row in grid)
    headers=[(column_letter(i),grid[header_row-1][i-1] if i-1<len(grid[header_row-1]) else "") for i in range(1,width+1)]
    validate_mapping(mapping,headers)
    header_text=dict(headers);index={letter:number for number,(letter,_) in enumerate(headers,1)}
    rows=[]
    for number,row in enumerate(grid[header_row:],header_row+1):
        cells={}
        for column,letter in mapping.items():
            position=index[letter]-1
            cells[column]=dict(column=column,header=header_text[letter],cell=letter+str(number),text=row[position] if position<len(row) else "")
        if not any(cell["text"] for cell in cells.values()):continue
        rows.append(dict(row_number=number,cells=cells))
    if not rows:raise ValueError("The chosen sheet has no data rows under the header")
    return rows,[dict(column=column,letter=letter,header=header_text[letter]) for column,letter in mapping.items()]
