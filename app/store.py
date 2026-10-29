import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "lexicon.sqlite3"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY, alias TEXT UNIQUE NOT NULL,
                    canonical TEXT NOT NULL, category TEXT NOT NULL, note TEXT NOT NULL,
                    needs_context INTEGER NOT NULL, source TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS candidates (
                    id INTEGER PRIMARY KEY, term TEXT UNIQUE NOT NULL,
                    document_count INTEGER NOT NULL, trigger_groups TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                );
                CREATE TABLE IF NOT EXISTS deleted_entries (alias TEXT PRIMARY KEY);
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(entries)")}
            if "expansion" not in columns:
                db.execute("ALTER TABLE entries ADD COLUMN expansion TEXT NOT NULL DEFAULT ''")
            if "provenance" not in columns:
                db.execute("ALTER TABLE entries ADD COLUMN provenance TEXT NOT NULL DEFAULT '[]'")
            if "evidence" not in columns:
                db.execute("ALTER TABLE entries ADD COLUMN evidence TEXT NOT NULL DEFAULT 'manual'")
            seeds = json.loads(Path(__file__).with_name("seeds.json").read_text("utf-8"))
            if not db.execute("SELECT 1 FROM meta WHERE key='seeded'").fetchone():
                db.executemany(
                    "INSERT INTO entries "
                    "(alias,expansion,canonical,category,note,needs_context,source) "
                    "VALUES(:alias,:expansion,:canonical,:category,:note,:needs_context,'starter')",
                    seeds,
                )
                db.execute("INSERT INTO meta VALUES('seeded',1)")
                db.execute("INSERT INTO meta VALUES('version',1)")
            if not db.execute("SELECT 1 FROM meta WHERE key='expansion_v1'").fetchone():
                for seed in seeds:
                    db.execute(
                        "UPDATE entries SET expansion=:expansion "
                        "WHERE alias=:alias AND source='starter' AND expansion=''",
                        seed,
                    )
                new_seed = next(seed for seed in seeds if seed["alias"] == "ㄷㄸ")
                db.execute(
                    "INSERT OR IGNORE INTO entries "
                    "(alias,expansion,canonical,category,note,needs_context,source) "
                    "VALUES(:alias,:expansion,:canonical,:category,:note,:needs_context,'starter')",
                    new_seed,
                )
                db.execute("INSERT INTO meta VALUES('expansion_v1',1)")
                db.execute("UPDATE meta SET value=value+1 WHERE key='version'")
            db.execute("UPDATE entries SET expansion=alias WHERE expansion=''")
            bundle_path = Path(__file__).parent / "data" / "lexicon.json"
            manifest = json.loads(bundle_path.with_name("manifest.json").read_text("utf-8"))
            raw = bundle_path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest != manifest["sha256"]:
                raise ValueError("배포 사전의 해시가 일치하지 않습니다.")
            marker = "bundle_" + digest
            if not db.execute("SELECT 1 FROM meta WHERE key=?", (marker,)).fetchone():
                sources = {s["id"]: s for s in manifest["sources"]}
                for item in json.loads(raw)["entries"]:
                    if db.execute(
                        "SELECT 1 FROM deleted_entries WHERE alias=?", (item["alias"],)
                    ).fetchone():
                        continue
                    item["provenance"] = json.dumps(
                        [sources[s] for s in item["sources"]], ensure_ascii=False
                    )
                    db.execute(
                        "INSERT OR IGNORE INTO entries "
                        "(alias,expansion,canonical,category,note,needs_context,"
                        "source,provenance,evidence) "
                        "VALUES(:alias,:expansion,:canonical,:category,:note,:needs_context,"
                        "'corpus',:provenance,:evidence)",
                        item,
                    )
                db.execute("INSERT INTO meta VALUES(?,1)", (marker,))
                db.execute("UPDATE meta SET value=value+1 WHERE key='version'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def entries(self):
        with self.connect() as db:
            result = [dict(row) for row in db.execute("SELECT * FROM entries ORDER BY id")]
            for entry in result:
                entry["provenance"] = json.loads(entry["provenance"])
            return result

    def version(self):
        with self.connect() as db:
            return db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0]

    def add(self, entry):
        with self.connect() as db:
            if db.execute("SELECT count(*) FROM entries").fetchone()[0] >= 5000:
                raise ValueError("사전은 최대 5,000개까지 등록할 수 있습니다.")
            cursor = db.execute(
                "INSERT INTO entries(alias,expansion,canonical,category,note,needs_context,source) "
                "VALUES(:alias,:expansion,:canonical,:category,:note,:needs_context,'user')",
                entry,
            )
            db.execute("UPDATE meta SET value=value+1 WHERE key='version'")
            db.execute("UPDATE candidates SET status='approved' WHERE term=?", (entry["alias"],))
            return cursor.lastrowid

    def delete(self, entry_id):
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO deleted_entries SELECT alias FROM entries WHERE id=?",
                (entry_id,),
            )
            deleted = db.execute("DELETE FROM entries WHERE id=?", (entry_id,)).rowcount
            if deleted:
                db.execute("UPDATE meta SET value=value+1 WHERE key='version'")
            return bool(deleted)

    def candidates(self):
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM candidates WHERE status='pending' "
                    "ORDER BY document_count DESC,id"
                )
            ]

    def save_candidates(self, candidates):
        # Counts describe the submitted batch; repeated submission must not inflate evidence.
        with self.connect() as db:
            for item in candidates:
                db.execute(
                    "INSERT INTO candidates(term,document_count,trigger_groups) VALUES(?,?,?) "
                    "ON CONFLICT(term) DO UPDATE SET "
                    "document_count=max(document_count,excluded.document_count), "
                    "trigger_groups=excluded.trigger_groups",
                    (item["term"], item["document_count"], ", ".join(item["trigger_groups"])),
                )

    def dismiss(self, candidate_id):
        with self.connect() as db:
            return bool(
                db.execute(
                    "UPDATE candidates SET status='dismissed' WHERE id=? AND status='pending'",
                    (candidate_id,),
                ).rowcount
            )
