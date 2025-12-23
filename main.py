import uvicorn
import os
from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# === 引入我们刚刚拆分的 5 个 Router ===
from backend.routers import (
    api_sql,           # 题库管理、知识审核
    api_search,        # RAG搜索、知识库管理
    api_import_books,  # 书本导入
    api_dingchun,      # 定春核心审题
    api_common,        # 日志、配置
    api_batch_review,
    api_AI_search,
    api_question_agent,
)

app = FastAPI()

# === CORS 配置 ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(content=b"", media_type="image/x-icon")

# === 【核心】注册路由 ===
app.include_router(api_sql.router)
app.include_router(api_search.router)
app.include_router(api_import_books.router)
app.include_router(api_dingchun.router)
app.include_router(api_common.router)
app.include_router(api_batch_review.router)
app.include_router(api_AI_search.router)
app.include_router(api_question_agent.router, prefix="")

# === 静态资源挂载 ===
if os.path.exists("resource"):
    app.mount("/resource", StaticFiles(directory="resource"), name="resource")
if os.path.exists("frontend"):
    app.mount("/", StaticFiles(directory="frontend", html=True), name="static")

if __name__ == "__main__":
    import os
    print(f"📂 当前工作目录: {os.getcwd()}")
    print("🚀 系统启动中... 端口 8000 (调试模式)")

    # ❌ [不要这样写] 这种写法会启动子进程，PyCharm 杀不掉
    # uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

    # ✅ [推荐写法] 直接传对象，不开启 reload，单进程运行
    # 这样 PyCharm 的停止按钮一按，进程必死。
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")