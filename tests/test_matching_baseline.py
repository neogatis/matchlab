import datetime
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app" / "legacy" / "matchlab_v7.py"

class BaselineLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["MATCH_DATA_DIR"] = cls.tmp.name
        os.environ["PRE_LAUNCH_MODE"] = "true"
        os.environ["ADMIN_IMPORT_KEY"] = "test-admin-key"
        spec = importlib.util.spec_from_file_location("matchlab_v7_test", SOURCE)
        cls.m = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.m
        spec.loader.exec_module(cls.m)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        c = self.m.db()
        for table in ["messages","date_proposals","matches","likes","blocks","reports","notifications","photos","answers","criteria","attribution","events","sessions","profiles","users"]:
            c.execute(f"DELETE FROM {table}")
        c.commit(); c.close()

    def add_user(self, uid, gender, seek, age, status="ACTIVE_SEARCH", eligibility="ACTIVE_FOR_MATCHING", completed=1):
        c = self.m.db()
        year = datetime.date.today().year - age
        dob = f"{year}-01-01"
        c.execute("INSERT INTO users(id,email,password_hash,created_at,referral_code) VALUES(?,?,?,?,?)",(uid,f"u{uid}@test.local","x",self.m.now(),f"r{uid}"))
        c.execute("""INSERT INTO profiles(user_id,display_name,dob,gender,seek_gender,city,relationship_status,eligibility_status,dating_goal,readiness_score,questionnaire_completed,profile_completed,updated_at)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(uid,f"U{uid}",dob,gender,seek,"Алматы",status,eligibility,"SERIOUS",100,1,completed,self.m.now()))
        c.execute("INSERT INTO criteria(user_id,data,updated_at) VALUES(?,?,?)",(uid,"{}",self.m.now()))
        for qid in range(1,65):
            c.execute("INSERT INTO answers(user_id,qid,value) VALUES(?,?,?)",(uid,qid,3))
        c.commit(); c.close()

    def test_questionnaire_is_64_unique_questions(self):
        self.assertEqual(len(self.m.QUESTIONS),64)
        self.assertEqual(len({q["text"] for q in self.m.QUESTIONS}),64)

    def test_readiness_score_bounds(self):
        self.assertEqual(self.m.readiness("YES","YES"),100)
        self.assertEqual(self.m.readiness("LOOK_ONLY","NO"),12)

    def test_relationship_status_blocks_matching(self):
        self.assertEqual(self.m.status_from_screen("YES","ACTIVE"),("IN_RELATIONSHIP","NOT_ACTIVE_FOR_MATCHING"))

    def test_mutual_gender_and_hard_filters_pass(self):
        self.add_user(1,"M","F",30)
        self.add_user(2,"F","M",28)
        c=self.m.db()
        self.assertTrue(self.m.hard_pass(c,1,2))
        c.close()

    def test_one_sided_hard_filter_blocks_pair(self):
        self.add_user(1,"M","F",30)
        self.add_user(2,"F","M",28)
        c=self.m.db()
        c.execute("UPDATE criteria SET data=? WHERE user_id=1",(json.dumps({"age":{"importance":"REQUIRED","min":18,"max":25}}),)); c.commit()
        self.assertFalse(self.m.hard_pass(c,1,2))
        c.close()

    def test_paused_profile_is_excluded(self):
        self.add_user(1,"M","F",30)
        self.add_user(2,"F","M",28,status="PAUSED",eligibility="NOT_ACTIVE_FOR_MATCHING")
        c=self.m.db(); self.assertFalse(self.m.hard_pass(c,1,2)); c.close()

    def test_blocked_pair_is_excluded(self):
        self.add_user(1,"M","F",30)
        self.add_user(2,"F","M",28)
        c=self.m.db(); c.execute("INSERT INTO blocks(blocker,blocked,created_at) VALUES(?,?,?)",(2,1,self.m.now())); c.commit()
        self.assertFalse(self.m.hard_pass(c,1,2)); c.close()

if __name__ == "__main__":
    unittest.main()
