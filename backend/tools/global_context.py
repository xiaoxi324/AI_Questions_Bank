import contextvars

# 定义一个上下文变量，用于存储当前请求的日志队列
# 默认值为 None，这样在非 Web 环境下运行也不会报错
log_queue_ctx = contextvars.ContextVar("log_queue", default=None)