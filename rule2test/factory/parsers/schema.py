"""Version 1 tabular import schema. Rule rows sharing an ID form an AND group."""
MANIFEST_KEYS=("schema_version","created_at","created_by")
POLICY_COLUMNS=("label","table_id","version","hit_policy","default_outcome","default_amount","default_deductible","currency","as_of")
RULE_COLUMNS=("rule_id","version","title","field","operator","value_type","value","currency","outcome","payout_amount","deductible","effective_from","effective_to","quote")
TEST_COLUMNS=("test_id","revision","title","inputs_json","expected_outcome","expected_amount","currency","rule_ids","kind","rationale")
SHEETS={"Policies":POLICY_COLUMNS,"RulesV1":RULE_COLUMNS,"RulesV2":RULE_COLUMNS,"Tests":TEST_COLUMNS}
JSON_KEYS={"policies":"Policies","rules_v1":"RulesV1","rules_v2":"RulesV2","tests":"Tests"}
