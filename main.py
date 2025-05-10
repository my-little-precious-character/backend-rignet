import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
import os
import shutil
from typing import Dict
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

######## global variables ########

# queue & task
task_queue = asyncio.Queue()
task_progress: Dict[str, str] = {} # [task_id, queued | processing | done]

######## worker ########

async def handle_rigging(task):
    task_progress[task.id] = "processing (10%)"

    try:
        # Copy obj file to rig
        src = os.path.join(UPLOAD_DIR, f"{task.id}_mesh.obj")
        dst = os.path.join("/workspace/RigNet/quick_start", f"{task.id}_ori.obj")
        shutil.copyfile(src, dst)

        # Rig
        proc = await asyncio.create_subprocess_exec(
            "/usr/local/bin/python", "quick_start.py", task.id,
            cwd="/workspace/RigNet",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Wait the subprocess
        task_progress[task.id] = "processing (50%)"
        stdout, stderr = await proc.communicate()

        # Check exit code
        if proc.returncode != 0:
            task_progress[task.id] = "error"
            print(f"[{task.id}] STDERR:\n{stderr.decode()}")
            return

        # Copy rig output to results dir
        rig_txt_src = os.path.join("/workspace/RigNet/quick_start", f"{task.id}_ori_rig.txt")
        rig_txt_dst = os.path.join(UPLOAD_DIR, f"{task.id}_ori_rig.txt")
        shutil.copyfile(rig_txt_src, rig_txt_dst)

        # Combind obj and rig result
        blender_proc = await asyncio.create_subprocess_exec(
            "/blender/blender", "--background", "--python", "utils/blender_save_fbx.py", "--", "uploads", task.id,
            cwd="/app",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        task_progress[task.id] = "processing (90%)"
        b_stdout, b_stderr = await blender_proc.communicate()

        # Check exit code
        if blender_proc.returncode != 0:
            task_progress[task.id] = "error"
            print(f"[{task.id}] blender error:\n{b_stderr.decode()}")
            return

    except Exception as e:
        task_progress[task.id] = "error"
        print(f"[{task.id}] Exception: {e}")

async def handle_rigging_test(task):
    print("hi")
    for i in range(100):
        await asyncio.sleep(0.01)
        task_progress[task.id] = f"processing ({(i + 1) * 1}%)"

    src = os.path.join("results-sample", "luigi.fbx")
    dst = os.path.join(UPLOAD_DIR, f"{task.id}.fbx")
    shutil.copyfile(src, dst)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async def worker():
        while True:
            task: TaskItem = await task_queue.get()
            task_progress[task.id] = "processing"
            try:
                if task.type == TaskType.RIGGING:
                    await handle_rigging(task)
                elif task.type == TaskType.RIGGING_TEST:
                    await handle_rigging_test(task)
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
async def upload_image(
    obj: UploadFile = File(...),
    mtl: UploadFile = File(...),
    albedo: UploadFile = File(...),
    prev_task_id: str = Form(...),
    mode: str = "prod"):
    # Generate filename
    task_id = prev_task_id

    # Save the .obj
    obj_path  = os.path.join(UPLOAD_DIR, f"{task_id}_mesh.obj")
    with open(obj_path, "wb") as f:
        f.write(await obj.read())

    # Save the .mtl
    mtl_path  = os.path.join(UPLOAD_DIR, f"{task_id}_mesh.mtl")
    with open(mtl_path, "wb") as f:
        f.write(await mtl.read())

    # Save the albedo texture
    alb_path   = os.path.join(UPLOAD_DIR, f"{task_id}_mesh_albedo.png")
    with open(alb_path, "wb") as f:
        f.write(await albedo.read())

    task_type = TaskType.RIGGING if mode == "prod" else TaskType.RIGGING_TEST
    task = TaskItem(
        id=task_id,
        type=task_type,
        data={
            "obj_path": obj_path,
            "mtl_path": mtl_path,
            "alb_path": alb_path,
        }
    )
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

    path = os.path.join(UPLOAD_DIR, f"{task_id}.fbx")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path, media_type="application/octet-stream", filename=os.path.basename(path))
