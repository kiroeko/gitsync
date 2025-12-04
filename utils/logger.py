import os
import threading
from datetime import datetime
from filelock import FileLock

class Logger:
    """一个纯类方法 + 类状态的静态单例 Logger，不允许实例化"""
    
    _file_path: str | None = None

    _init_lock = threading.Lock()
    _initialized = False

    _lock_path: str | None = None

    def __new__(cls, *args, **kwargs):
        raise TypeError("Logger is a singleton static class. Use Logger.init() instead.")

    @classmethod
    def init(cls, folder_path: str):
        with cls._init_lock:
            if cls._initialized:
                # 第二次调用直接忽略，保持幂等性
                return

            # 确认文件夹存在
            os.makedirs(folder_path, exist_ok=True)

            utc_str = cls._utc_now()  # 带时区格式，例如 2025-11-28T11-15-50-993595+0800
            cls._file_path = os.path.abspath(os.path.join(folder_path, f"{utc_str}.log"))
            cls._lock_path = os.path.abspath(os.path.join(folder_path, f"{utc_str}.lock"))

            # 存在文件 → 删除
            if os.path.exists(cls._file_path):
                os.remove(cls._file_path)

            # 创建空文件 + 写入创建时间
            lock = FileLock(cls._lock_path)
            with lock:
                with open(cls._file_path, "w", encoding="utf-8") as f:
                    f.write(f"# Log created at {utc_str}\n\n")
                    f.flush()
                    os.fsync(f.fileno())

            # 打印日志文件绝对路径
            print(f"Logger initialized. Log file: {cls._file_path}")

            cls._initialized = True

    @staticmethod
    def _utc_now():
        return datetime.now().astimezone().strftime("%Y-%m-%dT%H-%M-%S-%f%z")

    @classmethod
    def _write(cls, level: str, message: str, extra: dict | None):
        try:
            ts = cls._utc_now()
            log_line = f"{ts} | {level} | {message} | {extra}\n\n"

            if not cls._initialized:
                raise RuntimeError("Logger.init(file_path) must be called before using logger.")

            lock = FileLock(cls._lock_path)
            with lock:
                with open(cls._file_path, "a", encoding="utf-8") as f:
                    f.write(log_line)
                    f.flush()
                    os.fsync(f.fileno())
        except Exception as e:
            print(f"Log write warning: {e}")
            return False
        finally:
            print(log_line)

    # ------- public API -------
    @classmethod
    def info(cls, message: str, extra: dict | None = None):
        cls._write("info", message, extra)

    @classmethod
    def warning(cls, message: str, extra: dict | None = None):
        cls._write("warning", message, extra)

    @classmethod
    def error(cls, message: str, extra: dict | None = None):
        cls._write("error", message, extra)


# 用例
# def main():
#     # 初始化日志系统，只需调用一次
#     Logger.init("logs/")

#     # 写一些日志
#     Logger.log("程序启动")
#     Logger.warning("CPU 使用率偏高", {"cpu": "85%"})
#     Logger.error("发生严重错误", {"code": 500, "reason": "未知异常"})

#     print("日志已写入文件夹 logs/ 下自动生成的 UTC 文件名中")

# if __name__ == "__main__":
#     main()