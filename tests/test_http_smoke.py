import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app" / "legacy" / "matchlab_v7.py"

def free_port():
    s=socket.socket(); s.bind(("127.0.0.1",0)); p=s.getsockname()[1]; s.close(); return p

class HttpSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); cls.port=free_port()
        env=os.environ.copy(); env.update({"MATCH_DATA_DIR":cls.tmp.name,"PORT":str(cls.port),"PRE_LAUNCH_MODE":"true","ADMIN_IMPORT_KEY":"test-admin-key"})
        cls.proc=subprocess.Popen([sys.executable,"-u",str(SOURCE)],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        cls.base=f"http://127.0.0.1:{cls.port}"
        deadline=time.time()+8
        while time.time()<deadline:
            try:
                with urllib.request.urlopen(cls.base+"/health",timeout=.5) as r:
                    if r.status==200: return
            except Exception: time.sleep(.1)
        raise RuntimeError("server did not become healthy")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try: cls.proc.wait(timeout=3)
        except subprocess.TimeoutExpired: cls.proc.kill()
        cls.tmp.cleanup()

    def request(self,path,body=None,cookie=None):
        data=None if body is None else json.dumps(body).encode()
        req=urllib.request.Request(self.base+path,data=data,headers={"Content-Type":"application/json",**({"Cookie":cookie} if cookie else {})})
        try:
            r=urllib.request.urlopen(req,timeout=2); return r.status,dict(r.headers),json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code,dict(e.headers),json.loads(e.read())

    def test_health_reports_prelaunch_and_question_count(self):
        status,_,j=self.request("/health")
        self.assertEqual(status,200); self.assertEqual(j["questions"],64); self.assertEqual(j["unique"],64); self.assertEqual(j["prelaunch"],"true")

    def test_underage_registration_rejected(self):
        status,_,j=self.request("/api/register",{"email":"minor@test.local","password":"abcdef","display_name":"Minor","dob":"2012-01-01","gender":"M","seek_gender":"F","city":"Алматы","relationship":"NO","open_to":"ACTIVE"})
        self.assertEqual(status,400); self.assertIn("18+",j["error"])

    def test_adult_registration_and_questions(self):
        status,h,j=self.request("/api/register",{"email":"adult@test.local","password":"abcdef","display_name":"Adult","dob":"1995-01-01","gender":"M","seek_gender":"F","city":"Алматы","relationship":"NO","open_to":"ACTIVE"})
        self.assertEqual(status,201)
        cookie=h.get("Set-Cookie").split(";",1)[0]
        status,_,q=self.request("/api/questions",cookie=cookie)
        self.assertEqual(status,200); self.assertEqual(len(q["questions"]),64); self.assertEqual(len({x["text"] for x in q["questions"]}),64)
        status,_,feed=self.request("/api/feed",cookie=cookie)
        self.assertEqual(status,200); self.assertTrue(feed["prelaunch"]); self.assertFalse(feed["matching_enabled"]); self.assertEqual(feed["items"],[])

if __name__ == "__main__":
    unittest.main()
