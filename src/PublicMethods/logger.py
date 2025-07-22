import logging
import os
from datetime import datetime
import colorlog

# 定义日志文件存放目录
LOG_DIR = 'Logs'
Log_NAME = 'logger'
# 全局变量，用于存储本次运行的唯一日志文件路径，确保所有文件处理器指向同一个文件
_GLOBAL_LOG_FILE_PATH = None
# 不输出该方法内部的日志输出
logging.getLogger('urllib3.connectionpool').setLevel(logging.INFO)
logging.getLogger('httpcore').setLevel(logging.INFO)
logging.getLogger('telegram.ext').setLevel(logging.INFO)
logging.getLogger('httpx').setLevel(logging.WARN)

def _get_unique_log_file_path(log_folder=LOG_DIR, log_name=Log_NAME):
    """
    获取一个基于时间戳的唯一日志文件路径。
    这个函数只负责生成路径，不创建文件处理器。
    """
    if not os.path.exists(log_folder):
        os.makedirs(log_folder)
    l = os.path.join(log_folder, f"{log_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    return l


# 新增的全局日志配置函数，只在程序启动时调用一次
def setup_log(log_level=logging.INFO, log_name: str = None):
    """
    统一设置项目的全局日志配置。该函数应在应用程序启动时只被调用一次。
    它配置了根Logger的Handlers，所有其他Logger实例都会继承其传播行为。
    """
    global _GLOBAL_LOG_FILE_PATH

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # !!! 关键改动：只在根Logger没有Handlers时才添加，避免重复配置 !!!
    if not root_logger.handlers:
        # 1. 配置控制台输出 (带颜色)
        log_colors_config = {
            'DEBUG': 'cyan',  # 确保DEBUG级别也有颜色
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',  # 使用bold_red更突出
        }
        # 格式化器中添加 %(name)s 来显示是哪个模块发出的日志
        color_fmt = "%(log_color)s[%(asctime)s][%(name)s][%(filename)s][line:%(lineno)d]-%(levelname)s: %(message)s"
        console_handler = colorlog.StreamHandler()
        console_formatter = colorlog.ColoredFormatter(color_fmt, log_colors=log_colors_config,
                                                      datefmt='%Y-%m-%d %H:%M:%S')
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

        # 2. 配置文件输出
        # 只在第一次 setup 时生成唯一的日志文件路径
        if _GLOBAL_LOG_FILE_PATH is None:
            _GLOBAL_LOG_FILE_PATH = _get_unique_log_file_path(log_name=log_name or Log_NAME)

        file_handler = logging.FileHandler(filename=_GLOBAL_LOG_FILE_PATH, encoding="utf-8", mode='a')
        # 格式化器中添加 %(name)s 来显示是哪个模块发出的日志
        fmt = "[%(asctime)s][%(name)s][%(filename)s][line:%(lineno)d]-%(levelname)s: %(message)s"
        file_formatter = logging.Formatter(fmt, datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)


# 简化 get_logger 函数，它现在只负责获取 Logger 实例，不添加 Handler
def get_logger(filename):
    """
    获取一个特定名称的logger实例。
    推荐在每个模块的顶部使用 logger = get_logger(__name__)。
    这个函数不再负责添加Handlers，Handlers由 setup_global_logging 统一配置。
    """
    # 获取指定名称的Logger实例。
    # filename 参数将作为Logger的名称 (name)。
    logger = logging.getLogger(filename)
    # 子Logger的级别通常可以不设置，会继承父Logger (最终是root_logger) 的级别。
    # 如果需要为特定模块设置更低的级别 (如DEBUG)，可以在这里设置:
    # logger.setLevel(logging.DEBUG)
    return logger
