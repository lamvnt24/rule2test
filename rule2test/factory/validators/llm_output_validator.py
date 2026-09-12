"""Validate proposal shape and literal source citations; never approve AI output."""
from factory.models import Rule
from factory.models.common import require
import hashlib

def validate_rule_proposal(payload, documents):
    """documents maps document_id to exact source bytes, decoded as UTF-8 text here.
    Binary XLSX/PDF ingestion must supply verified source references via future parsers.
    """
    rule=Rule.from_dict(payload)
    for source in rule.sources:
        require(source.document_id in documents,"Missing source document")
        data=documents[source.document_id]
        require(type(data) is bytes,"Document must be bytes")
        require(hashlib.sha256(data).hexdigest()==source.document_hash,"Document hash mismatch")
        try: text=data.decode("utf-8")
        except UnicodeDecodeError: raise ValueError("This validator supports UTF-8 text only")
        require(source.quote in text,"Source quote not found")
    return rule
