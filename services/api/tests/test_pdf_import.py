"""Resource-boundary tests for trusted PDF parsing; no arbitrary source executes."""
import io
import subprocess
import pytest
from pypdf import PdfWriter
from app import pdf_import
from test_domain_api import database, logged


def upload(client,content):
    return client.post("/api/v1/candidate/resume-import",files={"file":("resume.pdf",content,"application/pdf")})


def pdf_bytes(pages=1,encrypted=False):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612,height=792)
    if encrypted:
        writer.encrypt("synthetic-password")
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


def test_real_unicode_pdf_reimports_with_exact_skill_offsets(database):
    client = logged()
    client.patch("/api/v1/candidate/profile",json={"title":"Разработчик API · резюме",
        "skills":["PYTHON","React","sql"]})
    exported = client.get("/api/v1/candidate/profile.pdf")
    result = upload(client,exported.content)
    assert result.status_code == 200,result.text
    values = result.json()
    assert values["source"] == "SELF_DECLARED" and not values["persisted"]
    assert len(values["source_text"]) <= 40_000 and "ФСП" in values["source_text"]
    spans = {item["value"]:item for item in values["source_spans"]}
    assert spans["Python"]["quote"] == "PYTHON" and spans["SQL"]["quote"] == "sql"
    for item in spans.values():
        assert values["source_text"][item["start"]:item["end"]] == item["quote"]
    profile = client.get("/api/v1/candidate/profile").json()
    assert profile["confirmed_grade"] is None and not profile["published"]


@pytest.mark.parametrize("content,code",[
    (b"%PDF-1.7\nmalformed truncated PDF","PDF_PARSE_FAILED"),
    (pdf_bytes(encrypted=True),"PDF_ENCRYPTED"),
    (pdf_bytes(pages=16),"PDF_PAGE_LIMIT")])
def test_invalid_encrypted_and_page_overflow_are_rejected(database,content,code):
    result = upload(logged(),content)
    assert result.status_code == 400 and result.json()["code"] == code


def test_blank_pdf_has_explicit_manual_fallback(database):
    result = upload(logged(),pdf_bytes())
    assert result.status_code == 422 and result.json()["code"] == "PDF_NO_TEXT"


def test_timeout_terminates_only_the_owned_fake_parser_process(database,monkeypatch):
    monkeypatch.setattr(pdf_import,"WINDOWS_PLATFORM",False)
    created = []
    class OwnedTestProcess:
        returncode = None
        killed = False
        calls = 0
        def __init__(self,args,**kwargs):
            assert isinstance(args,list) and args[1] == "-I" and args[2].endswith("pdf_parser_worker.py")
            assert kwargs["shell"] is False
            assert "DATABASE_URL" not in kwargs["env"] and "OIDC_CLIENT_SECRET" not in kwargs["env"]
            created.append(self)
        def communicate(self,input=None,timeout=None):
            self.calls += 1
            if self.calls == 1:
                assert timeout == 6 and input.startswith(b"%PDF-")
                raise subprocess.TimeoutExpired("fixed-trusted-parser",timeout)
            assert self.killed
            return b"",b""
        def kill(self):
            self.killed,self.returncode = True,-9
        def poll(self): return self.returncode
        def wait(self,timeout=None): return self.returncode
    monkeypatch.setattr(pdf_import,"PROCESS_FACTORY",OwnedTestProcess)
    result = upload(logged(),pdf_bytes())
    assert result.status_code == 422 and result.json()["code"] == "PDF_PARSE_TIMEOUT"
    assert len(created) == 1 and created[0].killed and created[0].calls == 2


def test_slot_exhaustion_is_explicit_and_does_not_spawn(database,monkeypatch):
    class OccupiedSlots:
        def acquire(self,blocking):
            assert not blocking
            return False
        def release(self): raise AssertionError("Cannot release a slot not acquired")
    monkeypatch.setattr(pdf_import,"PARSER_SLOTS",OccupiedSlots())
    monkeypatch.setattr(pdf_import,"PROCESS_FACTORY",lambda *args,**kwargs:pytest.fail("Busy parser must not spawn"))
    result = upload(logged(),pdf_bytes())
    assert result.status_code == 503 and result.json()["code"] == "PDF_PARSER_BUSY"


def test_oversized_child_result_is_rejected(database,monkeypatch):
    monkeypatch.setattr(pdf_import,"WINDOWS_PLATFORM",False)
    class BoundedTestProcess:
        returncode = 0
        def __init__(self,*args,**kwargs): pass
        def communicate(self,**kwargs): return b"x" * (pdf_import.MAX_RESULT_BYTES+1),b""
        def poll(self): return 0
    monkeypatch.setattr(pdf_import,"PROCESS_FACTORY",BoundedTestProcess)
    result = upload(logged(),pdf_bytes())
    assert result.status_code == 400 and result.json()["code"] == "PDF_RESULT_LIMIT"


def test_windows_job_assignment_failure_closes_job_kills_only_owned_child_without_input(database,monkeypatch):
    class KernelFunction:
        def __init__(self,handler): self.handler = handler
        def __call__(self,*args): return self.handler(*args)
    calls = []
    class TestKernel:
        CreateJobObjectW = KernelFunction(lambda *args:7001)
        SetInformationJobObject = KernelFunction(lambda *args:True)
        AssignProcessToJobObject = KernelFunction(lambda *args:calls.append(("assign",args)) or False)
        CloseHandle = KernelFunction(lambda handle:calls.append(("close",handle)) or True)
    created = []
    class OwnedProcess:
        _handle = 9001
        returncode = None
        def __init__(self,*args,**kwargs): created.append(self)
        def communicate(self,**kwargs): pytest.fail("Cannot send PDF to an unrestricted parser")
        def poll(self): return self.returncode
        def kill(self): self.returncode = -9
        def wait(self,**kwargs): return self.returncode
    monkeypatch.setattr(pdf_import,"WINDOWS_PLATFORM",True)
    monkeypatch.setattr(pdf_import,"WINDOWS_KERNEL_FACTORY",lambda:TestKernel())
    monkeypatch.setattr(pdf_import,"PROCESS_FACTORY",OwnedProcess)
    result = upload(logged(),pdf_bytes())
    assert result.status_code == 503 and result.json()["code"] == "PDF_PARSER_ISOLATION_UNAVAILABLE"
    assert calls == [("assign",(7001,9001)),("close",7001)]
    assert len(created) == 1 and created[0].returncode == -9
