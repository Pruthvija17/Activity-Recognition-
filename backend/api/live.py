"""Live camera monitoring: session control and the frame WebSocket.

Protocol on /ws/live/{experiment_id}:
  client -> server  binary JPEG frame      server -> client  {"type": "result", ...}
  client -> server  text "stop"            server -> client  {"type": "summary", ...} then close
Invalid frames get {"type": "error"}; the session continues. If the socket drops, the session is
finalised anyway so no data is lost.
"""
import asyncio
import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from runtime import ai_pipeline, live

log = logging.getLogger("bas.live")

router = APIRouter(tags=["live"])


class StartLive(BaseModel):
    fps: float = Field(5.0, ge=1.0, le=10.0)
    name: Optional[str] = Field(None, max_length=120)


@router.post("/api/live/sessions", status_code=201)
async def start_session(body: StartLive):
    if not ai_pipeline.model_ready:
        raise HTTPException(status_code=503,
                            detail="Required AI model is missing. Check backend/weights/. " + (ai_pipeline.load_error or ""))
    try:
        session = await asyncio.to_thread(live.start, body.fps, body.name)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"experiment_id": session.experiment_id, "fps": session.fps,
            "ws_path": f"/ws/live/{session.experiment_id}"}


@router.get("/api/live/sessions/current")
def current_session():
    s = live.current
    if s is None:
        return None
    return {
        "experiment_id": s.experiment_id,
        # "finalizing": frames stopped, events are being segmented and saved.
        "state": "finalizing" if s.finished else "running",
        "fps": s.fps,
        "frames": s.frame_index,
        "seconds": round(s.written / s.fps, 1),
        "people": len(s.labels),
        "idle_seconds": round(time.monotonic() - s.last_frame_at, 1),
    }


@router.post("/api/live/sessions/{experiment_id}/stop")
async def stop_session(experiment_id: str):
    summary = await asyncio.to_thread(live.stop, experiment_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="No running live session with that id.")
    return summary


@router.websocket("/ws/live/{experiment_id}")
async def live_socket(ws: WebSocket, experiment_id: str):
    await ws.accept()
    session = live.get(experiment_id)
    if session is None:
        await ws.send_json({"type": "error", "message": "No running live session with that id."})
        await ws.close(code=4404)
        return
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            data = msg.get("bytes")
            if data is None:
                if (msg.get("text") or "").strip() == "stop":
                    break
                continue
            try:
                result = await asyncio.to_thread(session.process, data)
            except ValueError as e:
                await ws.send_json({"type": "error", "message": str(e)})
                continue
            except RuntimeError:
                break
            await ws.send_json(result)
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("Live socket error for %s", experiment_id)
    finally:
        summary = await asyncio.to_thread(live.stop, experiment_id)
        try:
            if summary:
                await ws.send_json({"type": "summary", **summary})
            await ws.close()
        except Exception:
            pass  # client already gone; the session is saved regardless
