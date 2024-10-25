from fastapi import FastAPI, HTTPException, BackgroundTasks, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import os
from AutoGenBook import BookGenerator
import uvicorn

app = FastAPI(
    title="AutoGenBook API",
    description="本の自動生成APIサービス",
)

class BookRequest(BaseModel):
    book_content: str
    target_readers: str
    n_pages: int
    level: Optional[int] = None

class BookResponse(BaseModel):
    status: str
    message: str
    task_id: str
    output_dir: Optional[str] = None

# 進行状況を保存する辞書
task_status = {}

def generate_book_task(task_id: str, request: BookRequest):
    try:
        bookgenerator = BookGenerator()
        
        # 初期化
        bookgenerator.initialize(request.book_content, request.target_readers, request.n_pages)

        if request.level:
            bookgenerator.set_equation_frequency_level(request.level)

        # 本の概要を生成
        bookgenerator.generate_book_title_and_summary()
        
        # 本の中身を生成
        bookgenerator.generate_book_detail()
        
        # PDFを生成
        bookgenerator.create_pdf()

        # タスクの状態を更新
        task_status[task_id] = {
            "status": "completed",
            "output_dir": bookgenerator.home_dir,
            "title": bookgenerator.book_node["title"]
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
    task_status[task_id] = {"status": "processing"}
    
    # バックグラウンドタスクとして本の生成を開始
    background_tasks.add_task(generate_book_task, task_id, request)
    
    return {
        "status": "accepted",
        "message": "本の生成を開始しました",
        "task_id": task_id
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

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8100, reload=True)
