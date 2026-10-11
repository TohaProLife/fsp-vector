"""Trusted data-only PDF parser process; receives bytes, emits bounded JSON.

No user source, shell, external renderer, URLs or files are executed. This is a
resource boundary for a PDF library, not a general-purpose execution sandbox.
"""
import io
import json
import sys
from pathlib import Path

MAX_PDF_BYTES = 3 * 1024 * 1024
MAX_TEXT = 40_000
MAX_RESULT_BYTES = 256 * 1024


def resource_limits():
    if sys.platform == "linux":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def parse(content):
    from pypdf import PdfReader
    if len(content) > MAX_PDF_BYTES:
        return {"ok":False,"code":"PDF_SIZE_LIMIT"}
    if not content.startswith(b"%PDF-"):
        return {"ok":False,"code":"PDF_PARSE_FAILED"}
    try:
        reader = PdfReader(io.BytesIO(content),strict=True)
        if reader.is_encrypted:
            return {"ok":False,"code":"PDF_ENCRYPTED"}
        pages = len(reader.pages)
        if not 1 <= pages <= 15:
            return {"ok":False,"code":"PDF_PAGE_LIMIT"}
        parts,remaining = [],MAX_TEXT
        for page in reader.pages:
            if remaining <= 0:
                break
            # Library allocation/decompression is confined to this bounded child.
            part = (page.extract_text() or "")[:min(20_000,remaining)]
            parts.append(part)
            remaining -= len(part) + 1
        return {"ok":True,"pages":pages,"text":"\n".join(parts)[:MAX_TEXT]}
    except (Exception,MemoryError):
        return {"ok":False,"code":"PDF_PARSE_FAILED"}


def main():
    resource_limits()
    # Passed exclusively by the trusted parent adapter, never derived from PDF or
    # a request field; -I disables ambient PYTHONPATH and user-site dependencies.
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir() or Path(sys.argv[1]).name != "site-packages":
        sys.stdout.buffer.write(b'{"ok":false,"code":"PDF_PARSE_FAILED"}')
        return
    sys.path.insert(0,sys.argv[1])
    content = sys.stdin.buffer.read(MAX_PDF_BYTES + 1)
    result = parse(content)
    encoded = json.dumps(result,ensure_ascii=True,separators=(",",":")).encode("ascii")
    # ASCII Unicode escaping may produce six bytes per character; 40k text stays
    # inside this protocol bound. No traceback or user-controlled log is returned.
    if len(encoded) > MAX_RESULT_BYTES:
        encoded = b'{"ok":false,"code":"PDF_RESULT_LIMIT"}'
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
