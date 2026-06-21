from fastapi import APIRouter, WebSocket
import base64

router = APIRouter()

@router.websocket("/media-stream")
async def media_stream(ws: WebSocket):
    await ws.accept()

    audio_buffer = bytearray()

    while True:
        msg = await ws.receive_json()

        event = msg.get("event")

        if event == "media":
            payload = msg["media"]["payload"]

            audio_buffer.extend(
                base64.b64decode(payload)
            )

        elif event == "stop":
            break