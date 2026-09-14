"""A plain test-case sheet: any header wording, any header row, every cell kept with its coordinate."""
import importlib.util,unittest
from io import BytesIO
from factory.parsers.common import ImportFailure
from factory.parsers.testcase_parser import inspect,extract_rows,suggest_mapping,cell_text,column_letter
from factory.parsers.testcase_samples import csv_bytes,sample_file,ROWS,rule_examples

EXCEL=importlib.util.find_spec("openpyxl") is not None

class MappingTests(unittest.TestCase):
    def test_english_and_vietnamese_headers_are_recognised(self):
        english=suggest_mapping([("A","Test Case ID"),("B","Title"),("C","Preconditions"),("D","Steps"),("E","Test Data"),("F","Expected Result")])
        self.assertEqual(english,{"test_id":"A","title":"B","preconditions":"C","steps":"D","test_data":"E","expected":"F"})
        vietnamese=suggest_mapping([("A","STT"),("B","Mã test"),("C","Tên test"),("D","Điều kiện"),("E","Các bước"),("F","Dữ liệu"),("G","Kết quả mong đợi")])
        self.assertEqual(vietnamese,{"test_id":"B","title":"C","preconditions":"D","steps":"E","test_data":"F","expected":"G"})
    def test_longest_match_wins_and_a_column_is_used_once(self):
        self.assertEqual(suggest_mapping([("A","ID"),("B","Expected Result"),("C","Result")]),{"test_id":"A","expected":"B"})
    def test_letters_and_cell_text(self):
        self.assertEqual([column_letter(i) for i in (1,26,27,52,53)],["A","Z","AA","AZ","BA"])
        self.assertEqual(cell_text(60.0),"60");self.assertEqual(cell_text(1.5),"1.5");self.assertEqual(cell_text(True),"TRUE");self.assertEqual(cell_text(None),"")

class CsvTests(unittest.TestCase):
    def test_inspect_preview_and_rows(self):
        info=inspect(csv_bytes("eligibility"),"cases.csv")
        sheet=info["sheets"][0]
        self.assertEqual((sheet["name"],sheet["header_row"],sheet["rows"]),("CSV",1,5))
        self.assertEqual(sheet["suggested"]["test_data"],"E");self.assertEqual(sheet["preview"][0][0],"TC001")
        rows,columns=extract_rows(csv_bytes("eligibility"),"cases.csv","CSV",sheet["suggested"])
        self.assertEqual(rows[1]["cells"]["test_data"],dict(column="test_data",header="Test Data",cell="E3",text="Tuổi: 61"))
        self.assertEqual({c["column"]:c["letter"] for c in columns},sheet["suggested"])
    def test_mapping_is_validated(self):
        data=csv_bytes("eligibility")
        for mapping,fragment in (({"expected":"F","title":"F"},"cannot feed two fields"),({"test_data":"E"},"expected-result"),({"expected":"Z"},"column letters"),({"bogus":"A","expected":"F"},"test-case columns")):
            with self.subTest(mapping=mapping),self.assertRaises(ValueError) as ctx:extract_rows(data,"cases.csv","CSV",mapping)
            self.assertIn(fragment,str(ctx.exception))
        with self.assertRaises(ValueError):extract_rows(data,"cases.csv","Missing",{"expected":"F"})
    def test_unsupported_and_empty_files_are_rejected(self):
        with self.assertRaises(ImportFailure):inspect(b"x","cases.txt")
        with self.assertRaises(ImportFailure):inspect(b"\n\n","cases.csv")
        with self.assertRaises(ImportFailure):inspect(b"\xff\xfe",("cases.csv"))

@unittest.skipUnless(EXCEL,"Install requirements-excel.txt")
class WorkbookTests(unittest.TestCase):
    def test_sample_workbook_round_trips(self):
        name,data=sample_file("eligibility")
        self.assertTrue(name.endswith(".xlsx"))
        info=inspect(data,name);sheet=info["sheets"][0]
        self.assertEqual(sheet["rows"],len(ROWS["eligibility"]))
        rows,_=extract_rows(data,name,sheet["name"],sheet["suggested"],sheet["header_row"])
        self.assertEqual([r["cells"]["expected"]["text"] for r in rows][:2],["Được chấp nhận","Bị từ chối"])
    def test_title_row_above_vietnamese_headers_is_detected(self):
        from openpyxl import Workbook
        workbook=Workbook();sheet=workbook.active;sheet.title="Kiểm thử"
        sheet.append(["Danh sách test case bảo hiểm"]);sheet.append([])
        sheet.append(["STT","Mã test","Tên test","Điều kiện","Các bước","Dữ liệu","Kết quả mong đợi"])
        sheet.append([1,"TC-A","Tuổi biên","","","Tuổi: 65","Được chấp nhận"]);sheet.append([2,"TC-B","","","",60,"Bị từ chối"])
        stream=BytesIO();workbook.save(stream)
        info=inspect(stream.getvalue(),"vn.xlsx");found=info["sheets"][0]
        self.assertEqual(found["header_row"],3);self.assertEqual(found["suggested"]["test_id"],"B");self.assertEqual(found["rows"],2)
        rows,_=extract_rows(stream.getvalue(),"vn.xlsx","Kiểm thử",found["suggested"],3)
        self.assertEqual(rows[1]["cells"]["test_data"]["text"],"60","numeric cells read as plain text")
        self.assertEqual(rows[0]["cells"]["expected"]["cell"],"G4")
    def test_macros_are_refused(self):
        name,data=sample_file("eligibility")
        with self.assertRaises(ImportFailure):inspect(data.replace(b"xl/workbook.xml",b"xl/vbaProject.bin"),name)

class ExampleTests(unittest.TestCase):
    def test_examples_cover_vietnamese_and_japanese_pairs(self):
        examples=rule_examples()
        self.assertEqual(len(examples),6);self.assertEqual({e["engine"] for e in examples},{"pattern","provider"})
        self.assertTrue(all(e["current"] and e["new"] and e["current"]!=e["new"] for e in examples))



# Additional regression coverage for the independent-intake UI.
import unittest
from factory.parsers.testcase_parser import inspect,extract_rows
from factory.parsers.testcase_samples import csv_bytes,xlsx_bytes

class AdditionalTestcaseParserTests(unittest.TestCase):
    def test_csv_has_no_rules_and_preserves_cells(self):
        data=csv_bytes('eligibility'); info=inspect(data,'tests.csv')['sheets'][0]
        rows,_=extract_rows(data,'tests.csv','CSV',info['suggested'])
        self.assertEqual(len(rows),5)
        self.assertEqual(rows[1]['cells']['test_data']['cell'],'E3')
        self.assertEqual(rows[1]['cells']['expected']['text'],'Bị từ chối')

    def test_mapping_must_not_reuse_column(self):
        with self.assertRaises(ValueError):
            extract_rows(csv_bytes('eligibility'),'tests.csv','CSV',{'test_data':'E','expected':'E'})

    def test_blank_csv_row_does_not_shift_source_location(self):
        data=b'Test Data,Expected Result\nAge: 60,Accepted\n\nAge: 61,Denied\n'
        rows,_=extract_rows(data,'tests.csv','CSV',{'test_data':'A','expected':'B'})
        self.assertEqual(rows[-1]['cells']['test_data']['cell'],'A4')

    def test_xlsx_matches_csv(self):
        try: import openpyxl
        except ImportError: self.skipTest('openpyxl not installed')
        info=inspect(xlsx_bytes('eligibility'),'tests.xlsx')['sheets'][0]
        rows,_=extract_rows(xlsx_bytes('eligibility'),'tests.xlsx',info['name'],info['suggested'])
        self.assertEqual(len(rows),5)
        self.assertEqual(rows[-1]['cells']['test_id']['cell'],'A6')
