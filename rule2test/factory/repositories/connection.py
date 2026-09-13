"""SQLite migration and transaction boundary. Uses wf_ tables beside the legacy demo."""
import sqlite3,time
from pathlib import Path
from contextlib import contextmanager
from factory.observability import metrics
from factory.exceptions import ConflictError,ConfigurationError

_MIGRATION_1=(
    "CREATE TABLE wf_objects(scope TEXT NOT NULL,kind TEXT NOT NULL,entity_id TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL,hash TEXT NOT NULL,PRIMARY KEY(scope,kind,entity_id,revision))",
    "CREATE TABLE wf_heads(workflow_id TEXT PRIMARY KEY,revision INTEGER NOT NULL)",
    "CREATE TABLE wf_runs(workflow_id TEXT NOT NULL,run_id TEXT NOT NULL,payload TEXT NOT NULL,hash TEXT NOT NULL,PRIMARY KEY(workflow_id,run_id),FOREIGN KEY(workflow_id) REFERENCES wf_heads(workflow_id))",
    "CREATE TABLE wf_events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,workflow_id TEXT NOT NULL,revision INTEGER NOT NULL,actor TEXT NOT NULL,event TEXT NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL,FOREIGN KEY(workflow_id) REFERENCES wf_heads(workflow_id))",
)

class Database:
    def __init__(self,path):
        if str(path)==":memory:":raise ConfigurationError("Use a file-backed SQLite path; sessions open separate connections")
        self.path=Path(path).resolve()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.transaction() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS wf_schema_migrations(version INTEGER PRIMARY KEY)")
            versions={r[0] for r in connection.execute("SELECT version FROM wf_schema_migrations")}
            if versions-{1,2}:raise ConfigurationError("Database contains an unsupported workflow migration")
            if 1 not in versions:
                for statement in _MIGRATION_1:connection.execute(statement)
                connection.execute("INSERT INTO wf_schema_migrations VALUES(1)")
            if 2 not in versions:
                connection.execute("CREATE TABLE wf_source_documents(workflow_id TEXT NOT NULL,document_hash TEXT NOT NULL,metadata TEXT NOT NULL,data BLOB NOT NULL,PRIMARY KEY(workflow_id,document_hash),FOREIGN KEY(workflow_id) REFERENCES wf_heads(workflow_id))")
                connection.execute("INSERT INTO wf_schema_migrations VALUES(2)")

    def _connect(self):
        c=sqlite3.connect(self.path,timeout=10,isolation_level=None)
        c.execute("PRAGMA foreign_keys=ON");c.execute("PRAGMA busy_timeout=10000")
        c.row_factory=sqlite3.Row
        return c

    @contextmanager
    def transaction(self):
        c=self._connect();started=time.perf_counter();outcome="ok"
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except sqlite3.IntegrityError as exc:
            outcome="conflict";c.rollback();raise ConflictError("SQLite integrity conflict") from exc
        except Exception:
            outcome="error";c.rollback();raise
        finally:
            c.close()
            metrics.increment("db_transactions_total",outcome=outcome)
            metrics.observe("db_transaction_duration_ms",(time.perf_counter()-started)*1000,outcome=outcome)

    @contextmanager
    def read(self):
        c=self._connect();started=time.perf_counter();outcome="ok"
        try:
            c.execute("BEGIN")
            yield c
            c.commit()
        except Exception:
            outcome="error";raise
        finally:
            c.close()
            metrics.increment("db_reads_total",outcome=outcome)
            metrics.observe("db_read_duration_ms",(time.perf_counter()-started)*1000,outcome=outcome)