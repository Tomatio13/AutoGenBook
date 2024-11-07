from fastapi import FastAPI, HTTPException, BackgroundTasks, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import os
from AutoGenBook import BookGenerator
from utils.models import llms
import uvicorn
import glob

app = FastAPI(
    title="AutoGenBook API",
    description="本の自動生成APIサービス",
)

class BookRequest(BaseModel):
    book_content: str
    target_readers: str
    n_pages: int
    level: Optional[int] = None
    wav_output: Optional[int] = 0

class BookResponse(BaseModel):
    status: str
    message: str
    task_id: str
    output_dir: Optional[str] = None
    author: Optional[str] = None

# 進行状況を保存する辞書
task_status = {}

def generate_book_task(task_id: str, request: BookRequest):
    try:
        bookgenerator = BookGenerator()
        llm = llms()
        author = f"{llm.get_provider_name()}:{llm.get_model_name()}"
        
        # 初期化
        bookgenerator.initialize(request.book_content, request.target_readers, request.n_pages)

        if request.level:
            bookgenerator.set_equation_frequency_level(request.level)

        # 本の概要を生成
        bookgenerator.generate_book_title_and_summary()
        
        # 本の中身を生成
        bookgenerator.generate_book_detail()
        
        # PDFを生成
        filename = bookgenerator.create_pdf()

        # wavファイルを生成
        if request.wav_output > 0:
            wav_filename = bookgenerator.create_wav(filename,request.wav_output)
            if wav_filename:
                wav_files = glob.glob(os.path.join(bookgenerator.home_dir, "*.wav"))
                if wav_files:
                    wav_path = wav_files[0]
                    wav_filename = os.path.basename(wav_path)
                else:
                    wav_filename = None
                    wav_path = None
        else:
            wav_filename = None
            wav_path = None
        # カバー画像のパスを取得（.png ファイルを検索）
        cover_files = glob.glob(os.path.join(bookgenerator.home_dir, "*.png"))
        if cover_files:
            cover_path = cover_files[0]  # 完全なパス
            cover_filename = os.path.basename(cover_path)  # ファイル名のみ
        else:
            cover_path = None
            cover_filename = None

        # タスクの状態を更新
        task_status[task_id] = {
            "status": "completed",
            "output_dir": bookgenerator.home_dir,
            "title": bookgenerator.book_node["title"],
            "cover_path": cover_path,
            "cover_filename": cover_filename,
            "wav_path": wav_path,
            "wav_filename": wav_filename,
            "author": author
        }

    except Exception as e:
        task_status[task_id] = {
            "status": "failed",
            "error": str(e)
        }

@app.post("/generate-book", response_model=BookResponse)
async def generate_book(request: BookRequest, background_tasks: BackgroundTasks):
    import uuid
    task_id = str(uuid.uuid4())
    
    # タスクの初期状態を設定
    task_status[task_id] = {
        "status": "processing",
        "author": None
    }
    
    # バックグラウンドタスクとして本の生成を開始
    background_tasks.add_task(generate_book_task, task_id, request)
    
    return {
        "status": "accepted",
        "message": "本の生成を開始しました",
        "task_id": task_id,
        "author": None
    }

@app.get("/task/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = task_status[task_id]
    if task["status"] == "failed":
        raise HTTPException(status_code=500, detail=task["error"])
    
    return task

@app.get("/download/{task_id}")
async def download_book(task_id: str):
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = task_status[task_id]
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="Book generation is not completed")
    
    # PDFファイルのパスを構築
    pdf_path = os.path.join(task["output_dir"], f"{task['title']}.pdf")
    
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF file not found")
    
    return FileResponse(
        path=pdf_path,
        filename=f"{task['title']}.pdf",
        media_type="application/pdf"
    )

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/download-cover/{task_id}")
async def download_cover(task_id: str):
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = task_status[task_id]
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="Book generation is not completed")
    
    if not task.get("cover_path"):
        raise HTTPException(status_code=404, detail="Cover image not found")
    
    return FileResponse(
        path=task["cover_path"],
        filename=task["cover_filename"],
        media_type="image/png"
    )

@app.get("/download-wav/{task_id}")
async def download_wav(task_id: str):
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = task_status[task_id]
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="Book generation is not completed")
    
    if not os.path.exists(task["wav_path"]):
        raise HTTPException(status_code=404, detail="WAV file not found")
    
    return FileResponse(path=task["wav_path"], filename=task["wav_filename"], media_type="audio/wav")   

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8100, reload=True)
