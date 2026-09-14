"""Rule sentences become cited, typed rule rows; anything unclear becomes a question."""
import json,unittest
from decimal import Decimal
from factory.models.extraction import SourceText,ExtractionRequest
from factory.providers.llm.patterns import PatternRuleProvider
from factory.providers.llm.factory import configured_provider
from factory.providers.llm.synthetic import SOURCE_PAIRS
from factory.services.rule_interpreter import interpret,rows
from factory.validators.extraction_validator import validate_response
from factory.parsers.testcase_samples import RULE_SENTENCES

def conditions(finding):return [(c.field,c.operator,str(c.value)) for c in finding.conditions]

class ShapeTests(unittest.TestCase):
    def found(self,text):
        finding,questions=interpret(text);self.assertIsNotNone(finding,questions);return finding
    def test_age_range_in_three_languages_with_or_without_diacritics(self):
        for text in ("Khách hàng từ 18 đến 65 tuổi được tham gia bảo hiểm.","Khach hang tu 18 den 65 tuoi duoc tham gia bao hiem",
                     "Customers aged 18 to 65 are eligible.","Age from 18 through 65 inclusive is allowed; otherwise denied.",
                     "Độ tuổi tham gia: 18-65 tuổi","Khách hàng dưới 18 tuổi hoặc trên 65 tuổi bị từ chối."):
            with self.subTest(text=text):
                finding=self.found(text)
                self.assertEqual((finding.shape,finding.outcome,finding.default),("age","allow","deny"))
                self.assertEqual(conditions(finding),[("age","ge","18"),("age","le","65")])
    def test_bounds_on_separate_lines_merge_with_their_own_citations(self):
        finding=self.found("Tuổi tối đa để tham gia là 65 tuổi.\nKhách hàng phải từ 18 tuổi trở lên mới được tham gia.")
        self.assertEqual([(c.operator,c.line) for c in finding.conditions],[("le",1),("ge",2)])
        self.assertEqual(self.found("Customers must be at least 18 years old to enrol.").conditions[0].operator,"ge")
    def test_claim_threshold(self):
        finding=self.found("Yêu cầu bồi thường trên 100.000.000 VND phải được xem xét thủ công.")
        self.assertEqual((finding.shape,finding.outcome,finding.default,finding.currency),("claim","review","allow","VND"))
        self.assertEqual(conditions(finding),[("claim_amount","gt","100000000")])
        self.assertEqual(self.found("Claims of 100,000,000 VND or more are reviewed manually.").conditions[0].operator,"ge")
        self.assertEqual(self.found("Yêu cầu bồi thường trên 150 triệu phải được xem xét thủ công.").conditions[0].value,Decimal("150000000"))
        inverse=self.found("Yêu cầu dưới 50 triệu được tự động duyệt; còn lại chuyển xem xét.")
        self.assertEqual((inverse.outcome,inverse.default,inverse.conditions[0].operator),("allow","review","lt"))
    def test_deductible(self):
        for text in ("Số tiền chi trả bằng số tiền yêu cầu trừ đi mức khấu trừ 5.000.000 VND, tối thiểu 0 VND.",
                     "Payout equals the claim amount minus a deductible of 5,000,000 VND, minimum 0.","Mức miễn thường là 5 triệu đồng."):
            with self.subTest(text=text):
                finding=self.found(text)
                self.assertEqual((finding.shape,finding.outcome,finding.default,finding.deductible),("deductible","payout","invalid",Decimal("5000000")))
    def test_japanese_fixtures_read_the_same_as_the_mock_replay(self):
        expected={"eligibility":[("age","ge","18"),("age","le","60")],"claim_review":[("claim_amount","gt","100000000")],"deductible":[("claim_amount","ge","0")]}
        for profile,(current,_) in SOURCE_PAIRS.items():
            with self.subTest(profile=profile):self.assertEqual(conditions(self.found(current)),expected[profile])
    def test_questions_instead_of_guesses(self):
        cases={"Khách hàng phải có hồ sơ hợp lệ.":"No rule pattern recognised","Khách hàng từ 65 đến 18 tuổi được tham gia.":"lower age 65 is above",
               "Khách hàng từ 18 đến 65 tuổi.":"not whether those customers are accepted","Claims over 100000000 require review.":"specify the currency",
               "Khách hàng từ 18 đến 65 tuổi được tham gia.\nYêu cầu trên 100 triệu phải xem xét.":"mixes different rule types",
               "Trên 100 triệu phải xem xét.\nTrên 200 triệu phải xem xét.":"both state a claim rule"}
        for text,fragment in cases.items():
            with self.subTest(text=text):
                finding,questions=interpret(text);self.assertIsNone(finding);self.assertIn(fragment," ".join(questions))
    def test_rows_follow_the_import_contract(self):
        policy,rule_rows=rows(self.found("Khách hàng từ 18 đến 65 tuổi được tham gia bảo hiểm."),"v2",2)
        self.assertEqual((policy["label"],policy["version"],policy["default_outcome"]),("v2",2,"deny"))
        self.assertEqual([(r["operator"],r["value"],r["quote"]) for r in rule_rows],[("ge",18,"Khách hàng từ 18 đến 65 tuổi được tham gia bảo hiểm."),("le",65,"Khách hàng từ 18 đến 65 tuổi được tham gia bảo hiểm.")])

class ProviderTests(unittest.TestCase):
    def request(self,current,new):
        sources=([SourceText(document_id="current-rule.txt",label="v1",text=current)] if current is not None else [])+[SourceText(document_id="new-rule.txt",label="v2",text=new)]
        return ExtractionRequest(sources=tuple(sources))
    def test_output_passes_the_citation_validator_for_every_demo_pair(self):
        for profile,(current,new) in RULE_SENTENCES.items():
            with self.subTest(profile=profile):
                request=self.request(current,new)
                data,citations=validate_response(PatternRuleProvider().extract(request,system_prompt="",timeout_seconds=1),request)
                self.assertEqual(data["status"],"ready");self.assertEqual(len(citations),len(data["rules_v1"])+len(data["rules_v2"])+2)
                self.assertTrue(all(row["version"]==2 for row in data["rules_v2"]))
    def test_new_rule_alone_is_a_single_version_proposal(self):
        request=self.request(None,"Yêu cầu bồi thường trên 150 triệu phải xem xét thủ công.")
        self.assertFalse(request.baseline_known)
        data,citations=validate_response(PatternRuleProvider().extract(request,system_prompt="",timeout_seconds=1),request)
        self.assertEqual([p["label"] for p in data["policies"]],["v2"]);self.assertEqual(data["rules_v1"],[]);self.assertEqual(len(citations),2)
    def test_questions_become_clarification_and_mismatched_shapes_are_refused(self):
        request=self.request("Khách hàng từ 18 đến 60 tuổi được tham gia.","Trên 100 triệu phải xem xét.")
        result=json.loads(PatternRuleProvider().extract(request,system_prompt="",timeout_seconds=1))
        self.assertEqual(result["status"],"needs_clarification");self.assertIn("both versions must describe the same rule",result["issues"][0])
        request=self.request("Khách hàng từ 18 đến 60 tuổi được tham gia.","Khách hàng từ 18 đến 65 tuổi.")
        result=json.loads(PatternRuleProvider().extract(request,system_prompt="",timeout_seconds=1))
        self.assertTrue(result["issues"][0].startswith("New rule:"));self.assertEqual(result["rules_v2"],[])
    def test_pattern_is_an_explicit_configuration_choice(self):
        self.assertEqual(configured_provider({"RULE2TEST_EXTRACTION_PROVIDER":"pattern"}).name,"pattern")
        self.assertEqual(configured_provider({}).name,"mock")

if __name__=="__main__":unittest.main()
