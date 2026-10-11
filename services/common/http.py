from fastapi import HTTPException, Request


async def bounded_body(request: Request, limit: int) -> bytes:
    chunks, total = [], 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise HTTPException(413, "Body limit exceeded")
        chunks.append(chunk)
    return b"".join(chunks)
