"""Bounded parent adapter; all subprocess code is a fixed trusted module."""
import json
import ctypes
import os
from ctypes import wintypes
import subprocess
import sys
import sysconfig
import threading
from pathlib import Path

PDF_TIMEOUT_SECONDS = 6
MAX_RESULT_BYTES = 256 * 1024
PARSER_SLOTS = threading.BoundedSemaphore(3)
PROCESS_FACTORY = subprocess.Popen
WINDOWS_PLATFORM = sys.platform == "win32"
WINDOWS_KERNEL_FACTORY = lambda: ctypes.WinDLL("kernel32",use_last_error=True)


class PdfImportFailure(Exception):
    def __init__(self,code):
        self.code = code


class BasicJobLimits(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit",ctypes.c_longlong),("PerJobUserTimeLimit",ctypes.c_longlong),
        ("LimitFlags",wintypes.DWORD),("MinimumWorkingSetSize",ctypes.c_size_t),
        ("MaximumWorkingSetSize",ctypes.c_size_t),("ActiveProcessLimit",wintypes.DWORD),
        ("Affinity",ctypes.c_size_t),("PriorityClass",wintypes.DWORD),("SchedulingClass",wintypes.DWORD)]


class JobIoCounters(ctypes.Structure):
    _fields_ = [(field,ctypes.c_ulonglong) for field in ("ReadOperationCount","WriteOperationCount",
        "OtherOperationCount","ReadTransferCount","WriteTransferCount","OtherTransferCount")]


class ExtendedJobLimits(ctypes.Structure):
    _fields_ = [("BasicLimitInformation",BasicJobLimits),("IoInfo",JobIoCounters),
        ("ProcessMemoryLimit",ctypes.c_size_t),("JobMemoryLimit",ctypes.c_size_t),
        ("PeakProcessMemoryUsed",ctypes.c_size_t),("PeakJobMemoryUsed",ctypes.c_size_t)]


class OwnedJob:
    def __init__(self,kernel,handle):
        self.kernel,self.handle = kernel,handle
    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def attach_windows_job(process):
    """Cap only the Popen child before its stdin receives any PDF bytes."""
    kernel = WINDOWS_KERNEL_FACTORY()
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p,wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE,wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateJobObjectW(None,None)
    if not handle:
        raise PdfImportFailure("PDF_PARSER_ISOLATION_UNAVAILABLE")
    job = OwnedJob(kernel,handle)
    limits = ExtendedJobLimits()
    limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x0100 | 0x0008  # kill-on-close, process memory, active process cap
    limits.BasicLimitInformation.ActiveProcessLimit = 1
    limits.ProcessMemoryLimit = 512 * 1024 * 1024
    try:
        configured = kernel.SetInformationJobObject(handle,9,ctypes.byref(limits),ctypes.sizeof(limits))
        # Popen's owned HANDLE is used directly; no PID search/OpenProcess exists.
        assigned = configured and kernel.AssignProcessToJobObject(handle,int(process._handle))
        if not assigned:
            raise PdfImportFailure("PDF_PARSER_ISOLATION_UNAVAILABLE")
        return job
    except Exception:
        job.close()
        raise


WINDOWS_JOB_FACTORY = attach_windows_job


def parse_pdf_isolated(content):
    if not PARSER_SLOTS.acquire(blocking=False):
        raise PdfImportFailure("PDF_PARSER_BUSY")
    process,job = None,None
    try:
        worker = Path(__file__).with_name("pdf_parser_worker.py").resolve()
        # Windows venv python.exe may be a launcher that creates another process.
        # Use the actual interpreter and its fixed trusted venv package directory
        # so the one-process job cap cannot reject that launcher child.
        executable = sys._base_executable if WINDOWS_PLATFORM else sys.executable
        child_env = {name:value for name,value in os.environ.items() if name.upper() in {"SYSTEMROOT","WINDIR","LANG","LC_ALL"}}
        process = PROCESS_FACTORY([executable,"-I",str(worker),sysconfig.get_path("purelib")],stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,shell=False,env=child_env,
                                  creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0) if WINDOWS_PLATFORM else 0)
        if WINDOWS_PLATFORM:
            try:
                job = WINDOWS_JOB_FACTORY(process)
            except (OSError,AttributeError,ValueError):
                raise PdfImportFailure("PDF_PARSER_ISOLATION_UNAVAILABLE") from None
        try:
            output,_ = process.communicate(input=content,timeout=PDF_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            # Only the process object created by this invocation is terminated.
            process.kill()
            process.communicate(timeout=2)
            raise PdfImportFailure("PDF_PARSE_TIMEOUT") from None
        if process.returncode != 0:
            raise PdfImportFailure("PDF_PARSE_FAILED")
        if len(output) > MAX_RESULT_BYTES:
            raise PdfImportFailure("PDF_RESULT_LIMIT")
        try:
            result = json.loads(output)
        except (ValueError,UnicodeError):
            raise PdfImportFailure("PDF_PARSE_FAILED") from None
        if not isinstance(result,dict) or result.get("ok") is not True:
            allowed = {"PDF_SIZE_LIMIT","PDF_ENCRYPTED","PDF_PAGE_LIMIT","PDF_PARSE_FAILED","PDF_RESULT_LIMIT"}
            code = result.get("code") if isinstance(result,dict) else None
            raise PdfImportFailure(code if code in allowed else "PDF_PARSE_FAILED")
        if not isinstance(result.get("text"),str) or len(result["text"]) > 40_000 or type(result.get("pages")) is not int or not 1 <= result["pages"] <= 15:
            raise PdfImportFailure("PDF_RESULT_LIMIT")
        return {"text":result["text"],"pages":result["pages"]}
    except (OSError,subprocess.SubprocessError):
        raise PdfImportFailure("PDF_PARSER_UNAVAILABLE") from None
    finally:
        if job is not None:
            # An anonymous job contains exactly this parser child. Closing it
            # terminates that child if still alive and releases its kernel handle.
            job.close()
        if process is not None and process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        PARSER_SLOTS.release()
