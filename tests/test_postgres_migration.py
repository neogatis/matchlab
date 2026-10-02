import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine, text

from scripts.import_v7_sqlite_to_postgres import import_database
from scripts.compare_v7_sqlite_postgres import compare_database


class PostgresMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["DATABASE_URL"]

    def setUp(self):
        engine = create_engine(self.url)
        with engine.begin() as c:
            for table in [
                "audit_logs","data_requests","consents","product_events","notifications",
                "marketing_attribution","moderation_actions","reports","blocks",
                "date_proposals","messages","conversations","match_score_components",
                "matches","interests","legacy_photo_blobs","photos",
                "legacy_partner_criteria","partner_preferences","questionnaire_answers",
                "questionnaire_questions","questionnaire_versions","user_status_history",
                "profiles","sessions","users","settings"
            ]:
                c.execute(text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE'))
        self.engine = engine

    def fixture(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        c = sqlite3.connect(tmp.name)
        c.executescript("""
        CREATE TABLE users(id INTEGER PRIMARY KEY,email TEXT,password_hash TEXT,created_at TEXT,referral_code TEXT,referred_by INTEGER,invites_sent INTEGER);
        CREATE TABLE sessions(token TEXT PRIMARY KEY,user_id INTEGER,created_at TEXT);
        CREATE TABLE profiles(user_id INTEGER PRIMARY KEY,display_name TEXT,dob TEXT,gender TEXT,seek_gender TEXT,city TEXT,relationship_status TEXT,eligibility_status TEXT,dating_goal TEXT,readiness_chat TEXT,readiness_offline TEXT,readiness_score INTEGER,bio TEXT,height INTEGER,smoking TEXT,alcohol TEXT,lifestyle TEXT,religion TEXT,nationality TEXT,children_attitude TEXT,children_plans TEXT,questionnaire_completed INTEGER,profile_completed INTEGER,status_confirmed_at TEXT,updated_at TEXT);
        CREATE TABLE criteria(user_id INTEGER PRIMARY KEY,data TEXT,updated_at TEXT);
        CREATE TABLE answers(user_id INTEGER,qid INTEGER,value INTEGER,PRIMARY KEY(user_id,qid));
        CREATE TABLE photos(id INTEGER PRIMARY KEY,user_id INTEGER,mime TEXT,data TEXT,is_main INTEGER,moderation_status TEXT,created_at TEXT);
        CREATE TABLE likes(from_user INTEGER,to_user INTEGER,created_at TEXT,PRIMARY KEY(from_user,to_user));
        CREATE TABLE matches(id INTEGER PRIMARY KEY,user1 INTEGER,user2 INTEGER,compatibility_score INTEGER,mutual_fit_score INTEGER,created_at TEXT);
        CREATE TABLE messages(id INTEGER PRIMARY KEY,match_id INTEGER,sender INTEGER,body TEXT,created_at TEXT,read_at TEXT);
        CREATE TABLE date_proposals(id INTEGER PRIMARY KEY,match_id INTEGER,proposer INTEGER,format TEXT,when_text TEXT,district TEXT,budget TEXT,note TEXT,status TEXT,created_at TEXT);
        CREATE TABLE blocks(blocker INTEGER,blocked INTEGER,created_at TEXT,PRIMARY KEY(blocker,blocked));
        CREATE TABLE reports(id INTEGER PRIMARY KEY,reporter INTEGER,target_user INTEGER,photo_id INTEGER,reason TEXT,created_at TEXT);
        CREATE TABLE attribution(user_id INTEGER PRIMARY KEY,utm_source TEXT,utm_medium TEXT,utm_campaign TEXT,utm_content TEXT,utm_term TEXT,referral_input TEXT);
        CREATE TABLE notifications(id INTEGER PRIMARY KEY,user_id INTEGER,kind TEXT,text TEXT,created_at TEXT,read_at TEXT);
        CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE events(id INTEGER PRIMARY KEY,user_id INTEGER,event_type TEXT,meta TEXT,created_at TEXT);
        """)
        now = datetime.now(timezone.utc).isoformat()
        users = [
            (1,"a@example.com","hash",now,"r1",None,2),
            (2,"b@example.com","hash",now,"r2",1,0),
        ]
        c.executemany("INSERT INTO users VALUES(?,?,?,?,?,?,?)", users)
        c.executemany("INSERT INTO sessions VALUES(?,?,?)", [("tok",1,now)])
        profiles = [
            (1,"A","1995-01-01","M","F","Алматы","ACTIVE_SEARCH","ACTIVE_FOR_MATCHING","SERIOUS","YES","YES",100,"bio",183,"NO","RARE","ACTIVE","","","OK","YES",1,1,now,now),
            (2,"B","1997-01-01","F","M","Алматы","OPEN_TO_MATCH","ACTIVE_FOR_MATCHING","SERIOUS","RATHER_YES","MAYBE",66,"bio",168,"NO","RARE","ACTIVE","","","OK","YES",1,1,now,now),
        ]
        c.executemany("INSERT INTO profiles VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", profiles)
        c.execute("INSERT INTO criteria VALUES(?,?,?)",(1,'{"age":{"min":25,"max":35,"importance":"REQUIRED"},"city":{"value":"Алматы","allow_other_city":false,"importance":"IMPORTANT"}}',now))
        c.execute("INSERT INTO criteria VALUES(?,?,?)",(2,'{"age":{"min":25,"max":40,"importance":"REQUIRED"}}',now))
        c.executemany("INSERT INTO answers VALUES(?,?,?)", [(u,q,3) for u in (1,2) for q in range(1,65)])
        c.executemany("INSERT INTO photos VALUES(?,?,?,?,?,?,?)", [
            (1,1,"image/jpeg","AAA",1,"APPROVED",now),(2,1,"image/jpeg","BBB",0,"PENDING",now),
            (3,2,"image/jpeg","CCC",1,"APPROVED",now),(4,2,"image/jpeg","DDD",0,"APPROVED",now),
        ])
        c.execute("INSERT INTO likes VALUES(?,?,?)",(1,2,now))
        c.execute("INSERT INTO matches VALUES(?,?,?,?,?,?)",(1,1,2,88,84,now))
        c.execute("INSERT INTO messages VALUES(?,?,?,?,?,?)",(1,1,1,"hello",now,None))
        c.execute("INSERT INTO date_proposals VALUES(?,?,?,?,?,?,?,?,?,?)",(1,1,1,"COFFEE","Friday","Center","MEDIUM","", "PENDING",now))
        c.execute("INSERT INTO attribution VALUES(?,?,?,?,?,?,?)",(1,"instagram","cpc","launch","a","term","ref"))
        c.execute("INSERT INTO notifications VALUES(?,?,?,?,?,?)",(1,1,"MATCH","Matched",now,None))
        c.executemany("INSERT INTO settings VALUES(?,?)",[("PRE_LAUNCH_MODE","true"),("PRELAUNCH_MATCHING_ENABLED","false")])
        c.execute("INSERT INTO events VALUES(?,?,?,?,?)",(1,1,"registration",'{"source":"test"}',now))
        c.commit(); c.close()
        return tmp.name

    def test_lossless_core_import_and_normalization(self):
        path = self.fixture()
        import_database(path, self.url)
        report = compare_database(path, self.url)
        self.assertTrue(report["ok"], report)
        self.assertTrue(all(x["ok"] for x in report["checks"].values()), report)
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text("SELECT count(*) FROM users")).scalar_one(),2)
            self.assertEqual(c.execute(text("SELECT count(*) FROM questionnaire_questions")).scalar_one(),64)
            self.assertEqual(c.execute(text("SELECT count(*) FROM questionnaire_answers")).scalar_one(),128)
            self.assertEqual(c.execute(text("SELECT count(*) FROM photos")).scalar_one(),4)
            self.assertEqual(c.execute(text("SELECT count(*) FROM legacy_photo_blobs")).scalar_one(),4)
            self.assertEqual(c.execute(text("SELECT base64_data FROM legacy_photo_blobs WHERE photo_id=1")).scalar_one(),"AAA")
            self.assertEqual(c.execute(text("SELECT importance FROM partner_preferences WHERE user_id=1 AND criterion_key='age'")).scalar_one(),"HARD")
            self.assertEqual(c.execute(text("SELECT importance FROM partner_preferences WHERE user_id=1 AND criterion_key='city'")).scalar_one(),"IMPORTANT")
            self.assertEqual(c.execute(text("SELECT algorithm_version FROM matches WHERE id=1")).scalar_one(),"legacy-v7")
            self.assertEqual(c.execute(text("SELECT count(*) FROM conversations")).scalar_one(),1)
            self.assertEqual(c.execute(text("SELECT body FROM messages WHERE id=1")).scalar_one(),"hello")
            self.assertEqual(c.execute(text("SELECT utm_source FROM marketing_attribution WHERE user_id=1")).scalar_one(),"instagram")
            self.assertEqual(c.execute(text("SELECT metadata_json->>'source' FROM product_events WHERE id=1")).scalar_one(),"test")


if __name__ == "__main__":
    unittest.main()
