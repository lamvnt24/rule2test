"""The test-case interpreter reads what a QA wrote, and asks instead of guessing."""
import unittest
from decimal import Decimal
from factory.models import ValueKind,Outcome
from factory.services.testcase_interpreter import read_inputs,read_expected,interpret
from factory.services.text_patterns import fold,find_money,grouped

class FoldingAndMoneyTests(unittest.TestCase):
    def test_fold_keeps_length_so_spans_quote_the_original(self):
        for text in ("Khách hàng từ 18 đến 65 tuổi được tham gia bảo hiểm.","TUỔI: 60","Số tiền: 1,5 tỷ đồng","年齢: 60歳"):
            self.assertEqual(len(fold(text)),len(text))
        self.assertEqual(fold("Khách hàng ĐỦ điều kiện"),"khach hang du dieu kien")
    def test_vietnamese_english_and_japanese_amounts(self):
        cases={"120.000.000 VND":("120000000","VND"),"150,000,000 VND":("150000000","VND"),"100 triệu đồng":("100000000","VND"),
               "1,5 tỷ":("1500000000",None),"5.000.001 đ":("5000001","VND"),"20 tr vnd":("20000000","VND"),"0 VND":("0","VND"),
               "請求金額が100000000 VNDを超える":("100000000","VND")}
        for text,(amount,currency) in cases.items():
            with self.subTest(text=text):
                found=find_money(fold(text))
                self.assertEqual((str(found[0][0]),found[0][1]),(amount,currency))
    def test_identifiers_are_not_amounts(self):
        self.assertEqual([str(a[0]) for a in find_money(fold("TC001 age 60"))],["60"])
    def test_grouping(self):
        self.assertEqual(grouped(Decimal("150000000")),"150,000,000");self.assertEqual(grouped(Decimal("1.50")),"1.5")

class InputTests(unittest.TestCase):
    def age(self,text):
        inputs,notes,questions=read_inputs(text)
        self.assertFalse(questions,questions);self.assertEqual(inputs[0].field,"age");return inputs[0].value
    def test_age_wordings(self):
        for text in ("Tuổi: 60","Tuổi = 60","Khách hàng 60 tuổi","age: 60","Age = 60","aged 60","年齢: 60","60 years old","tuoi 60"):
            with self.subTest(text=text):self.assertEqual(self.age(text).data,60)
    def test_negative_and_overflow_ages_stay_typed(self):
        self.assertEqual(self.age("Tuổi: -5").data,-5);self.assertEqual(self.age("Tuổi: 121").data,121)
    def test_empty_missing_and_text_are_robustness_inputs(self):
        self.assertIs(self.age("Tuổi: (để trống)").kind,ValueKind.NULL)
        self.assertIs(self.age("Age: null").kind,ValueKind.NULL)
        self.assertIs(self.age("Thiếu trường tuổi").kind,ValueKind.MISSING)
        self.assertIs(self.age("age missing").kind,ValueKind.MISSING)
        value=self.age('Tuổi: "abc"');self.assertIs(value.kind,ValueKind.TEXT);self.assertEqual(value.data,"abc")
    def test_claim_amounts(self):
        inputs,_,questions=read_inputs("Số tiền yêu cầu: 120.000.000 VND")
        self.assertFalse(questions);self.assertEqual(inputs[0].field,"claim_amount")
        self.assertEqual((inputs[0].value.data,inputs[0].value.currency),(Decimal("120000000"),"VND"))
        inputs,notes,questions=read_inputs("Yêu cầu bồi thường 100 triệu")
        self.assertEqual(inputs[0].value.data,Decimal("100000000"));self.assertIn("VND assumed",notes[0])
        inputs,notes,_=read_inputs("150,000,000 VND")
        self.assertEqual(inputs[0].field,"claim_amount");self.assertIn("No field name",notes[0])
    def test_missing_currency_without_a_vietnamese_cue_is_a_question(self):
        inputs,_,questions=read_inputs("claim_amount: 100000000")
        self.assertEqual(inputs,());self.assertIn("Currency missing",questions[0])
    def test_two_fields_in_one_cell(self):
        inputs,_,questions=read_inputs("Tuổi: 30; Số tiền: 5 triệu")
        self.assertEqual([x.field for x in inputs],["age","claim_amount"]);self.assertFalse(questions)
    def test_unreadable_wording_is_a_question_not_a_guess(self):
        inputs,_,questions=read_inputs("Tuổi: nhiều")
        self.assertEqual(inputs,());self.assertIn("Could not read a number",questions[0])
        self.assertEqual(read_inputs("Hồ sơ hợp lệ"),((),(),()))

class ExpectedTests(unittest.TestCase):
    def outcome(self,text):
        action,note=read_expected(text);self.assertIsNotNone(action,note);return action
    def test_outcome_wordings(self):
        cases={"Được chấp nhận":Outcome.ALLOW,"Accepted":Outcome.ALLOW,"Đủ điều kiện tham gia":Outcome.ALLOW,"Bị từ chối":Outcome.DENY,
               "Không được chấp nhận":Outcome.DENY,"Không đủ điều kiện":Outcome.DENY,"Rejected":Outcome.DENY,"Chuyển xem xét thủ công":Outcome.REVIEW,
               "Manual review":Outcome.REVIEW,"Không hợp lệ":Outcome.INVALID,"Invalid":Outcome.INVALID,"Lỗi dữ liệu":Outcome.INVALID}
        for text,expected in cases.items():
            with self.subTest(text=text):self.assertIs(self.outcome(text).outcome,expected)
    def test_payout_with_amount(self):
        action=self.outcome("Chi trả 15.000.000 VND")
        self.assertIs(action.outcome,Outcome.PAYOUT);self.assertEqual(action.amount.data,Decimal("15000000"))
        self.assertEqual(self.outcome("Payout 5,000,001 VND").amount.data,Decimal("5000001"))
        self.assertEqual(self.outcome("Chi trả 0 VND").amount.data,Decimal("0"))
    def test_ambiguous_blank_and_incomplete_are_questions(self):
        for text,fragment in (("Được chấp nhận nhưng cần xem xét","reads as both"),("Tùy trường hợp","Could not read"),("","blank"),
                              ("Không chi trả","no amount"),("Payout 100","no currency")):
            with self.subTest(text=text):
                action,note=read_expected(text);self.assertIsNone(action);self.assertIn(fragment,note)

class RowTests(unittest.TestCase):
    def test_clear_row_is_ready(self):
        inputs,expected,status,notes,questions=interpret({"title":"Khách hàng 61 tuổi","test_data":"Tuổi: 61","expected":"Bị từ chối"})
        self.assertEqual(status,"ready");self.assertEqual(inputs[0].value.data,61);self.assertIs(expected.outcome,Outcome.DENY)
        self.assertEqual(questions,());self.assertIn("“Tuổi: 61” → Age = 61",notes)
    def test_inputs_read_from_the_title_need_confirmation(self):
        inputs,expected,status,notes,questions=interpret({"title":"Khách hàng 60 tuổi","test_data":"","expected":"Được chấp nhận"})
        self.assertEqual(status,"needs_confirmation");self.assertEqual(inputs[0].value.data,60)
        self.assertTrue(any("Confirm the inputs read from the title" in q for q in questions))
    def test_unreadable_row_lists_every_question(self):
        inputs,expected,status,notes,questions=interpret({"title":"Khách hàng lớn tuổi","test_data":"Khách hàng cao tuổi","expected":"Tùy trường hợp"})
        self.assertEqual(status,"needs_confirmation");self.assertEqual(inputs,());self.assertIsNone(expected);self.assertEqual(len(questions),2)

if __name__=="__main__":unittest.main()
