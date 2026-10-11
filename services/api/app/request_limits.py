"""ASGI body limits apply even to chunked requests before multipart spooling."""
import json


class BodyLimitMiddleware:
    def __init__(self, app, limit=4 * 1024 * 1024):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)
        chunks, length = [], 0
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            if event["type"] != "http.request":
                continue
            length += len(event.get("body", b""))
            if length > self.limit:
                data = json.dumps({"type":"urn:vector:problem:body_limit","title":"Слишком большой запрос",
                    "status":413,"detail":"Запрос не должен превышать 4 МБ.","code":"BODY_TOO_LARGE",
                    "request_id":None},ensure_ascii=False).encode()
                await send({"type":"http.response.start","status":413,
                            "headers":[(b"content-type",b"application/problem+json"),(b"cache-control",b"no-store")]})
                await send({"type":"http.response.body","body":data})
                return
            chunks.append(event.get("body", b""))
            if not event.get("more_body", False):
                break
        body, delivered = b"".join(chunks), False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type":"http.request","body":body,"more_body":False}
            return await receive()

        await self.app(scope, bounded_receive, send)
