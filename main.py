import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
import os
from typing import Dict
from uuid import uuid4
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

######## type ########

class TaskType(str, Enum):
    RIGGING = "rigging"
    RIGGING_TEST = "rigging_test"

@dataclass
class TaskItem:
    id: str
    type: TaskType
    data: dict

######## env var ########

# Load .env
load_dotenv()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

RESULT_DIR = os.getenv("RESULT_DIR", "results")
os.makedirs(RESULT_DIR, exist_ok=True)

######## global variables ########

# queue & task
task_queue = asyncio.Queue()
task_progress: Dict[str, str] = {} # [task_id, queued | processing | done]
task_result_paths: Dict[str, str] = {}  # [task_id, file path]

######## worker ########

@asynccontextmanager
async def lifespan(app: FastAPI):
    async def worker():
        while True:
            task: TaskItem = await task_queue.get()
            task_progress[task.id] = "processing"
            try:
                if task.type == TaskType.RIGGING:
                    pass    # TODO: 실제 처리
                elif task.type == TaskType.RIGGING_TEST:
                    for i in range(100):
                        await asyncio.sleep(0.01)
                        task_progress[task.id] = f"processing ({(i + 1) * 1}%)"
                    task_result_paths[task.id] = "results/sample.fbx" # FIXME:
                task_progress[task.id] = "done"
            except Exception as e:
                task_progress[task.id] = f"error: {str(e)}"

    # Run wordker
    asyncio.create_task(worker())

    yield

######## fastapi ########

app = FastAPI(lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://my-character.cho0h5.org",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "welcome"}

@app.post("/rigging")
async def upload_image(file: UploadFile = File(...), mode: str = "prod"):
    # Generate filename
    task_id = uuid4().hex
    file_extension = os.path.splitext(file.filename)[1]
    file_path = os.path.join(UPLOAD_DIR, f"{task_id}{file_extension}")

    # Store file
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)

    task_type = TaskType.RIGGING if mode == "prod" else TaskType.RIGGING_TEST
    task = TaskItem(id=task_id, type=task_type, data={"image_path": file_path})
    await task_queue.put(task)
    task_progress[task_id] = "queued"

    # Response
    return {"task_id": task_id}

@app.websocket("/rigging/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        task_id = await websocket.receive_text()

        while True:
            await asyncio.sleep(0.01)
            status = task_progress.get(task_id, "unknown")

            await websocket.send_text(f"status: {status}")

            if status == "done" or status.startswith("error"):
                break;

    finally:
        await websocket.close()

@app.get("/rigging")
async def get_image_result(task_id: str):
    if task_progress.get(task_id) != "done":
        raise HTTPException(status_code=400, detail="Task not complete")

    path = task_result_paths.get(task_id)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path, media_type="application/octet-stream", filename=os.path.basename(path))
