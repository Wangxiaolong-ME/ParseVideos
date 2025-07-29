import os
import sys
import threading
import time
from typing import Optional, Dict, List
import requests
from queue import Queue
import logging

from PublicMethods.tools import prepared_to_curl

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """自定义下载错误类，用于表示下载过程中发生的特定错误。"""
    pass


class ProgressMonitor(threading.Thread):
    """
    下载进度监控线程，负责实时更新下载进度到控制台。
    """

    def __init__(self, total_bytes: int, downloaded_counter: List[int], lock: threading.Lock, interval: float = 0.05):
        """
        初始化进度监控器。

        参数:
            total_bytes (int): 文件总字节数。
            downloaded_counter (List[int]): 共享的已下载字节计数器（单元素列表，以便在线程间共享引用）。
            lock (threading.Lock): 用于保护 downloaded_counter 的线程锁。
            interval (float): 刷新进度显示的时间间隔（秒）。
        """
        super().__init__(daemon=True)  # 设置为守护线程，主程序退出时自动终止
        self.total = total_bytes
        self.downloaded = downloaded_counter
        self.lock = lock
        self.interval = interval
        self.start_time = time.time()
        self._stop_event = threading.Event()  # 用于线程优雅退出的事件
        logger.debug(f"进度监控器初始化完成。总大小: {Downloader._sizeof_fmt_static(self.total)}")

    def run(self):
        """
        线程执行体，循环更新下载进度。
        """
        while not self._stop_event.is_set():
            with self.lock:
                current_downloaded = self.downloaded[0]

            # 避免除以零
            elapsed_time = max(time.time() - self.start_time, 0.001)
            current_speed = current_downloaded / elapsed_time

            dl_str = Downloader._sizeof_fmt_static(current_downloaded)
            total_str = Downloader._sizeof_fmt_static(self.total)
            speed_str = Downloader._sizeof_fmt_static(current_speed) + '/s'

            # 计算百分比
            progress_percent = (current_downloaded / self.total * 100) if self.total > 0 else 0

            # 使用更丰富的进度显示格式
            # sys.stdout.write(f"\r下载进度: {dl_str}/{total_str} ({progress_percent:.2f}%)，平均速度: {speed_str}")
            # sys.stdout.flush()
            time.sleep(self.interval)

        # 线程停止后，最后一次刷新到 100% 并显示最终速度
        with self.lock:
            final_downloaded = self.downloaded[0]
        final_elapsed = max(time.time() - self.start_time, 0.001)
        final_speed = final_downloaded / final_elapsed

        dl_str = Downloader._sizeof_fmt_static(final_downloaded)
        total_str = Downloader._sizeof_fmt_static(self.total)
        speed_str = Downloader._sizeof_fmt_static(final_speed) + '/s'

        # 确保总大小为0时显示正确
        if self.total == 0:
            sys.stdout.write(f"\r下载完成: 0B/0B，平均速度: {speed_str} (文件大小为0或无法获取)\n")
        else:
            sys.stdout.write(f"\r下载完成: {dl_str}/{total_str} (100.00%)，平均速度: {speed_str}\n")
        sys.stdout.flush()
        logger.debug("进度监控器已停止并完成最终刷新。")

    def stop(self):
        """
        设置停止事件，通知线程优雅退出。
        """
        self._stop_event.set()
        logger.debug("进度监控器收到停止信号。")


class SegmentDownloader(threading.Thread):
    """
    分片下载线程类，用于并发下载文件的指定字节区间。
    """

    def __init__(self,
                 session: requests.Session,
                 url: str,
                 start_byte: int,
                 end_byte: int,
                 tmp_path: str,
                 queue: Queue,
                 headers: Dict[str, str],
                 downloaded_counter: List[int],
                 lock: threading.Lock,
                 max_retries: int = 3,
                 close_session_on_finish: bool = False):
        """
        初始化分片下载器。

        参数:
            session (requests.Session): requests.Session 对象，用于发起 HTTP 请求。
            url (str): 要下载的资源 URL（最终已处理重定向）。
            start_byte (int): 本分片起始字节位置（包含）。
            end_byte (int): 本分片结束字节位置（包含）。
            tmp_path (str): 本分片临时文件保存路径（.partN）。
            queue (Queue): Queue 对象，用于将下载结果（start_byte, tmp_path/None）回传给主线程。
            headers (Dict[str, str]): HTTP 请求头，会在此基础上添加 Range 字段。
            downloaded_counter (List[int]): 共享的已下载字节计数器（列表或其包装），用于进度统计。
            lock (threading.Lock): 线程锁，用于保护 downloaded_counter 的并发写入。
            max_retries (int): 每个分片最大重试次数。
            close_session_on_finish (bool): 是否在线程结束时关闭其使用的 session。
                                            仅当 session 是此线程独有且不会被复用时设置为 True。
        """
        super().__init__()
        self.session = session
        self.url = url
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.tmp_path = tmp_path
        self.queue = queue
        self.headers = headers.copy()  # 拷贝 headers 以便安全修改
        self.headers['Range'] = f"bytes={start_byte}-{end_byte}"
        self.max_retries = max_retries
        self.downloaded_ctr = downloaded_counter
        self.lock = lock
        self.close_session_on_finish = close_session_on_finish
        self.name = f"SegmentDownloader-{start_byte}-{end_byte}"  # 为线程命名，便于日志追踪
        logger.debug(f"分片下载线程 {self.name} 初始化完成。范围: {start_byte}-{end_byte}, 目标: {tmp_path}")

    def run(self):
        """
        线程执行体，负责下载指定字节范围的数据。
        """
        logger.debug(f"分片下载线程 {self.name} 开始下载。URL: {self.url}, Range: {self.headers['Range']}")
        for attempt in range(1, self.max_retries + 1):
            try:
                # 确保每次重试前检查文件是否存在，如果存在则尝试删除，避免追加
                if os.path.exists(self.tmp_path):
                    logger.warning(f"检测到分片临时文件 {self.tmp_path} 存在，尝试删除后重试。")
                    os.remove(self.tmp_path)

                # 设置更合理的超时，连接和读取分开
                with self.session.get(self.url, headers=self.headers, stream=True, timeout=(10, 30)) as r:
                    r.raise_for_status()  # 检查 HTTP 状态码，非 2xx 抛出异常

                    # 检查 Content-Range 头，确保服务器响应了正确的范围
                    content_range = r.headers.get('Content-Range')
                    if content_range:
                        # 示例: bytes 0-100/1000
                        try:
                            range_info = content_range.split(' ')[1].split('/')[0]
                            start, end = map(int, range_info.split('-'))
                            if not (start == self.start_byte and end == self.end_byte):
                                logger.warning(
                                    f"服务器返回的 Content-Range 不匹配请求范围。请求: {self.headers['Range']}, 响应: {content_range}"
                                )
                        except ValueError:
                            logger.warning(f"无法解析 Content-Range: {content_range}")

                    actual_downloaded_in_segment = 0
                    with open(self.tmp_path, 'wb') as f:
                        for chunk in r.iter_content(8192):  # 每次获取 8KB 数据
                            if not chunk:  # 跳过空块
                                continue
                            f.write(chunk)
                            chunk_len = len(chunk)
                            actual_downloaded_in_segment += chunk_len
                            # 累加到共享计数器
                            with self.lock:
                                self.downloaded_ctr[0] += chunk_len

                # 验证下载的分片大小是否与预期一致（如果 Content-Length 可用）
                expected_size = self.end_byte - self.start_byte + 1
                if actual_downloaded_in_segment != expected_size:
                    logger.warning(
                        f"分片 {self.name} 下载大小不匹配。预期: {expected_size}B, 实际: {actual_downloaded_in_segment}B。可能文件被截断或Range请求部分支持。"
                    )

                logger.debug(
                    f"分片下载线程 {self.name} 完成")
                self.queue.put((self.start_byte, self.tmp_path))  # 成功，将结果放入队列
                return  # 成功，退出线程
            except requests.exceptions.RequestException as e:
                # 捕获 requests 库相关的异常，更具体的错误信息
                logger.warning(
                    f"分片下载线程 {self.name} 请求失败 (尝试 {attempt}/{self.max_retries})。URL: {self.url}, Range: {self.headers['Range']}, 错误: {e}"
                )
            except IOError as e:
                # 文件写入错误
                logger.error(
                    f"分片下载线程 {self.name} 文件写入失败 (尝试 {attempt}/{self.max_retries})。文件: {self.tmp_path}, 错误: {e}"
                )
            except Exception as e:
                # 捕获其他未知异常
                logger.error(
                    f"分片下载线程 {self.name} 发生未知错误 (尝试 {attempt}/{self.max_retries})。错误类型: {type(e).__name__}, 错误详情: {e}",
                    exc_info=True
                )

            time.sleep(1 * attempt)  # 每次重试间隔递增

        # 所有重试失败，放入 None，通知主线程回退
        logger.error(f"分片下载线程 {self.name} 达到最大重试次数 ({self.max_retries}) 仍未能完成。将回退到单线程下载。")
        self.queue.put((self.start_byte, None))

    def __del__(self):
        """
        析构函数中尝试关闭 session，确保资源释放。
        仅当 session 是独占时才关闭。
        """
        if self.close_session_on_finish and self.session:
            try:
                self.session.close()
                logger.debug(f"分片下载线程 {self.name} 自动关闭了其 session。")
            except Exception as e:
                logger.warning(f"分片下载线程 {self.name} 关闭 session 失败: {e}")


class Downloader:
    """
    HTTP 文件下载器，支持多线程分片下载、进度显示、重定向跟踪及错误回退。
    """

    def __init__(self, session: Optional[requests.Session] = None, threads: int = 4):
        """
        初始化下载器。

        参数:
            threads (int): 多线程下载时使用的并发线程数。
            default_session (requests.Session, optional): 可选的默认 requests.Session 对象。
                                                        如果提供，下载器会复用此 Session 进行探测和单线程下载。
                                                        如果为 None，则会创建一个新的 Session。
        """
        if threads <= 0:
            raise ValueError("并发线程数必须大于0。")
        self.threads = threads
        self.default_session = session or requests.Session()
        logger.info(f"Downloader 初始化完成。默认并发线程数: {self.threads}")

    @staticmethod
    def _sizeof_fmt_static(num: float, suffix: str = 'B') -> str:
        """
        将字节数转换为可读格式（如 1.23MB）。

        参数:
            num (float): 字节数。
            suffix (str): 单位后缀，默认为 'B'。

        返回:
            str: 格式化后的字符串。
        """
        if num < 0:
            return f"-{Downloader._sizeof_fmt_static(abs(num), suffix)}"  # 处理负数

        for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y']:
            if abs(num) < 1024.0:
                return f"{num:.2f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.2f}Y{suffix}"  # 应该不会达到 YB 级别，但作为兜底

    def _get_final_url(
            self,
            url: str,
            headers: Optional[Dict[str, str]] = None,
            timeout: int = 15,
            max_redirects: int = 5,
            return_flag: Optional[str] = None,
            use_get=False,
            return_filed_url=False,
    ) -> str:
        """
        手动跟踪 301/302/307 等重定向，返回最终 200 OK 的下载链接。
        如重定向次数超过 max_redirects，则抛出 DownloadError。

        参数:
            url (str): 初始 URL。
            headers (Dict[str, str], optional): 请求头。
            timeout (int): 请求超时时间。
            max_redirects (int): 最大重定向次数。
            return_flag (str, optional): 如果重定向URL包含此标志，则提前返回。
            return_filed_url 返回最后失败的那个url

        返回:
            str: 最终的下载 URL。

        抛出:
            DownloadError: 如果达到最大重定向次数或请求失败。
        """
        current_url = url
        visited_urls = {url}  # 记录已访问的 URL，防止重定向循环

        logger.debug(f"开始跟踪重定向。初始URL: {current_url}")
        start_time = time.perf_counter()  # 记录开始时间

        for i in range(max_redirects):
            try:
                # 特殊情况使用 GET 请求
                if use_get:
                    resp = self.default_session.get(
                        current_url,
                        headers=headers or {},
                        timeout=timeout,
                        allow_redirects=False  # 禁止 requests 自动处理重定向
                    )
                else:
                    # 使用 HEAD 请求，只获取头部信息，减少带宽消耗
                    resp = self.default_session.head(
                        current_url,
                        headers=headers or {},
                        timeout=timeout,
                        allow_redirects=False  # 禁止 requests 自动处理重定向
                    )
                if not return_filed_url:
                    resp.raise_for_status()  # 检查 HTTP 状态码

                # 如果是重定向状态码
                if resp.status_code in (301, 302, 303, 307, 308) and 'Location' in resp.headers:
                    location = resp.headers['Location']
                    # 处理相对路径重定向
                    if not location.startswith(('http://', 'https://')):
                        from urllib.parse import urljoin
                        location = urljoin(current_url, location)

                    logger.debug(f"[Redirect {i + 1}/{max_redirects}] 从 {current_url} → {location}")

                    if return_flag and return_flag in location:
                        logger.info(f"检测到 return_flag '{return_flag}'，提前返回重定向URL: {location}")
                        return location

                    if location in visited_urls:
                        raise DownloadError(f"检测到重定向循环，URL: {location}")
                    visited_urls.add(location)
                    current_url = location
                    continue
                elif return_filed_url:
                    return current_url

                # 非重定向状态码，表示已找到最终资源
                # logger.debug(
                #     f"已找到最终URL: {current_url} (状态码: {resp.status_code}) (耗时: {time.perf_counter() - start_time:.4f}秒)")
                return current_url

            except requests.exceptions.Timeout as e:
                logger.error(f"跟踪重定向时请求超时: {e}. URL: {current_url}")
                raise DownloadError(f"跟踪重定向时请求超时: {e}") from e
            except requests.exceptions.RequestException as e:
                logger.error(f"跟踪重定向时发生网络或HTTP错误: {e}. URL: {current_url}")
                raise DownloadError(f"跟踪重定向时发生网络或HTTP错误: {e}") from e
            except Exception as e:
                logger.error(f"跟踪重定向时发生未知错误: {e}. URL: {current_url}", exc_info=True)
                raise DownloadError(f"跟踪重定向时发生未知错误: {e}") from e

        logger.error(f"超过 {max_redirects} 次重定向仍未拿到资源，最后 URL: {current_url}")
        raise DownloadError(
            f"超过 {max_redirects} 次重定向仍未拿到资源，最后 URL: {current_url}"
        )

    def download(
            self,
            url: str,
            path: str,
            headers: Optional[Dict[str, str]] = None,
            timeout: int = 60,
            max_redirects: int = 5,
            multi_session: bool = False,  # 默认开启多 Session 策略，更利于并发
            session_pool_size: Optional[int] = 1,  # 默认1
    ) -> str:
        """
        下载文件，先跟踪重定向，再根据文件大小和配置决定单/多线程下载。

        参数:
            url (str): 初始 URL（可能先返回 302）。
            path (str): 输出文件路径（不包含 .part 后缀）。
            headers (Dict[str, str], optional): HTTP 请求头。
            timeout (int): 下载总超时时间（秒）。
            max_redirects (int): 跟踪重定向的最大次数。为0直接下载,不重定向寻找URL
            multi_session (bool): 是否为每个并发下载线程使用独立的 requests.Session。
                                  如果为 True，且 session_pool_size 为 None，则每个线程创建新 Session。
                                  如果为 True，且 session_pool_size 非 None，则从池中复用 Session。
                                  如果为 False，则所有线程共享 default_session。
            session_pool_size (int, optional): Session 池大小。仅在 multi_session 为 True 时有效。
                                                如果为 None，则每个分片线程获得独立的 Session。

        返回:
            str: 成功下载后文件的最终路径。

        抛出:
            DownloadError: 如果下载过程中发生任何不可恢复的错误。
        """
        headers = headers or {}
        logger.info(f"开始下载:{url}")
        logger.info(f"保存路径:{path}")

        logger.debug(
            f"下载参数: headers={headers}, timeout={timeout}, max_redirects={max_redirects}, multi_session={multi_session}, session_pool_size={session_pool_size}")
        download_start_time = time.perf_counter()  # 记录开始时间
        if max_redirects == 0:
            return self._single_download(url, path, headers, timeout)

        # 1. 探测最终 URL 与文件大小
        try:
            logger.debug(f"开始获取final_url")
            final_url = self._get_final_url(url, headers, timeout, max_redirects)
            logger.debug(f"获取final_url :{final_url}")
            logger.debug(f"发起HEAD请求内容长度")
            resp_head = self.default_session.head(final_url, headers=headers, timeout=timeout)
            logger.debug(f"HEAD请求完成")
            resp_head.raise_for_status()  # 确保 HEAD 请求成功
            total_size = int(resp_head.headers.get('Content-Length', 0))
            # logger.info(f"文件最终URL: {final_url}, 文件总大小: {Downloader._sizeof_fmt_static(total_size)}")
            if total_size == 0:
                logger.warning("服务器返回的 Content-Length 为 0，可能文件为空或不支持。尝试单线程下载。")
                return self._single_download(final_url, path, headers, timeout)

            # 检查是否支持 Range 请求
            accept_ranges = resp_head.headers.get('Accept-Ranges')
            if not accept_ranges or 'bytes' not in accept_ranges.lower():
                logger.warning(f"服务器不支持 Range 请求 ({accept_ranges})，将尝试继续多线程下载")
                # return self._single_download(final_url, path, headers, timeout)

        except DownloadError as e:
            logger.error(f"获取最终 URL 或文件大小失败: {e}")
            raise DownloadError(f"预下载检查失败: {e}") from e
        except requests.exceptions.RequestException as e:
            logger.error(f"HEAD 请求失败，无法获取文件信息: {e}")
            raise DownloadError(f"HEAD 请求失败: {e}") from e
        except Exception as e:
            logger.error(f"文件预处理阶段发生未知错误: {e}", exc_info=True)
            raise DownloadError(f"文件预处理错误: {e}") from e

        # 2. 根据文件大小和并发数决定是否多线程下载
        if total_size < 1024 * 1024 * 2:  # 如果文件小于2MB，或者线程数设置为1，直接单线程下载
            logger.info(f"文件较小 ({Downloader._sizeof_fmt_static(total_size)}) 或线程数设置为1，使用单线程下载。")
            return self._single_download(final_url, path, headers, timeout)

        if self.threads == 1:
            logger.info("配置为单线程下载。")
            return self._single_download(final_url, path, headers, timeout)

        # 3. 构造 Session 池 (如果启用 multi_session)
        session_pool: List[requests.Session] = []
        if multi_session:
            pool_actual_size = session_pool_size if session_pool_size is not None else self.threads
            logger.info(f"启用多 Session 策略，Session 池大小: {pool_actual_size}")
            for i in range(pool_actual_size):
                sess = requests.Session()
                # 拷贝 default_session 的代理、cookie 等配置
                sess.trust_env = self.default_session.trust_env
                sess.proxies = self.default_session.proxies  # 复制代理设置
                sess.cookies = self.default_session.cookies  # 复制 cookies
                sess.headers.update(self.default_session.headers)  # 合并默认头
                session_pool.append(sess)
                logger.debug(f"Session 池: 创建 Session {i + 1}/{pool_actual_size}")
        else:
            logger.debug("禁用多 Session 策略，所有线程共享主 Session。")

        # 4. 初始化共享资源
        downloaded_counter = [0]  # 用列表包装以便在多线程中传递引用并修改
        lock = threading.Lock()
        queue = Queue()  # 用于分片线程将结果回传给主线程

        # 5. 启动进度监控
        monitor = ProgressMonitor(total_size, downloaded_counter, lock)
        monitor.start()
        logger.debug("进度监控线程已启动。")

        # 6. 分配分片并启动下载线程
        part_size = total_size // self.threads
        tmp_files_map = {}  # {start_byte: tmp_path} 存储分片信息
        segment_threads: List[SegmentDownloader] = []

        logger.debug(f"开始多线程分片下载，分片数量：{self.threads}")
        for i in range(self.threads):
            start_byte = i * part_size
            # 最后一个分片处理剩余部分
            end_byte = (i + 1) * part_size - 1 if i < self.threads - 1 else total_size - 1

            # 如果起始字节大于结束字节，说明文件太小，或者分片逻辑有问题
            if start_byte > end_byte:
                logger.warning(f"分片 {i} 的起始字节 {start_byte} 大于结束字节 {end_byte}，跳过此分片。")
                continue

            tmp_path = f"{path}.part{i}"
            tmp_files_map[start_byte] = tmp_path

            current_thread_session: requests.Session
            close_session_flag = False

            if multi_session:
                if session_pool_size is not None:
                    # 从 Session 池中获取 Session
                    current_thread_session = session_pool[i % session_pool_size]
                    logger.debug(f"分片 {i}: 从 Session 池中复用 Session (索引: {i % session_pool_size})")
                else:
                    # 每个线程创建独立的 Session
                    current_thread_session = requests.Session()
                    current_thread_session.trust_env = self.default_session.trust_env
                    current_thread_session.proxies = self.default_session.proxies
                    current_thread_session.cookies = self.default_session.cookies
                    current_thread_session.headers.update(self.default_session.headers)
                    close_session_flag = True  # 独立的 Session 应该由自身关闭
                    logger.debug(f"分片 {i}: 创建新的独立 Session")
            else:
                # 所有线程共享 default_session
                current_thread_session = self.default_session
                logger.debug(f"分片 {i}: 共享主 Session")

            t = SegmentDownloader(
                session=current_thread_session,
                url=final_url,
                start_byte=start_byte,
                end_byte=end_byte,
                tmp_path=tmp_path,
                queue=queue,
                headers=headers,
                downloaded_counter=downloaded_counter,
                lock=lock,
                close_session_on_finish=close_session_flag  # 告诉 SegmentDownloader 是否关闭其 Session
            )
            segment_threads.append(t)
            t.start()
            logger.debug(f"分片线程 {t.name} 已启动。下载范围: [{start_byte}-{end_byte}] 到 {tmp_path}")

        # 7. 等待分片线程完成，带超时保护
        all_segments_completed = True
        thread_join_start_time = time.time()
        for t in segment_threads:
            remaining_timeout = timeout - (time.time() - thread_join_start_time)
            if remaining_timeout <= 0:
                logger.warning(f"下载总超时 ({timeout}s) 已耗尽，未能等待所有分片线程完成。")
                all_segments_completed = False
                break
            t.join(remaining_timeout)  # 等待线程完成，设置超时

            if t.is_alive():  # 如果线程仍然存活，说明 join 超时了
                logger.warning(f"分片线程 {t.name} 未能在规定时间内完成下载，可能卡死或超时。")
                all_segments_completed = False
                break

        # 停止进度监控器
        monitor.stop()
        monitor.join(timeout=5)  # 给监控器一点时间完成最后的输出
        if monitor.is_alive():
            logger.warning("进度监控器未能在规定时间内停止。")

        # 关闭 Session 池中的所有 Session
        if multi_session and session_pool_size is not None:
            for i, sess in enumerate(session_pool):
                try:
                    sess.close()
                    logger.debug(f"Session 池: Session {i} 已关闭。")
                except Exception as e:
                    logger.warning(f"Session 池: 关闭 Session {i} 失败: {e}")

        if not all_segments_completed:
            logger.error("部分或所有分片线程未成功完成，回退到单线程下载。")
            self._cleanup_temp_files(list(tmp_files_map.values()))  # 清理已生成的分片文件
            return self._single_download(final_url, path, headers, timeout)

        # 8. 收集分片结果
        segments_results: Dict[int, Optional[str]] = {}
        while not queue.empty():
            start_b, tmp_p = queue.get()
            segments_results[start_b] = tmp_p

        # 检查是否有分片下载失败（结果为 None）
        if any(tmp_file is None for tmp_file in segments_results.values()):
            failed_segments = [s for s, t in segments_results.items() if t is None]
            logger.error(
                f"检测到 {len(failed_segments)} 个分片下载失败，将回退到单线程下载。失败分片起始字节: {failed_segments}")
            self._cleanup_temp_files(list(tmp_files_map.values()))  # 清理已生成的分片文件
            return self._single_download(final_url, path, headers, timeout)

        # 9. 合并分片
        final_merged_tmp_path = path + ".merged_tmp"
        try:
            with open(final_merged_tmp_path, 'wb') as outf:
                # 按照字节起始位置排序，确保合并顺序正确
                for start_b, tmp_file in sorted(segments_results.items(), key=lambda kv: kv[0]):
                    logger.debug(f"合并分片: 从 {tmp_file} (起始 {start_b}) 写入到 {final_merged_tmp_path}")
                    with open(tmp_file, 'rb') as inf:
                        outf.write(inf.read())
                    os.remove(tmp_file)  # 合并后删除临时分片文件
                    logger.debug(f"已删除临时分片文件: {tmp_file}")

            # 原子性替换最终文件
            os.replace(final_merged_tmp_path, path)
            logger.info(f"多线程下载成功并合并文件到: {path}")
            logger.info(
                f"下载任务完成: {path} (总耗时: {time.perf_counter() - download_start_time:.2f}秒)")  # 增加结束打点
            return path
        except IOError as e:
            logger.critical(f"文件合并或移动失败: {e}. 请检查磁盘空间或权限。", exc_info=True)
            self._cleanup_temp_files([final_merged_tmp_path])  # 尝试清理合并失败的临时文件
            raise DownloadError(f"文件合并失败: {e}") from e
        except Exception as e:
            logger.critical(f"合并分片过程中发生未知错误: {e}", exc_info=True)
            self._cleanup_temp_files([final_merged_tmp_path])
            raise DownloadError(f"合并分片未知错误: {e}") from e

    def _single_download(self, url: str, path: str, headers: Dict[str, str], timeout: int, skip_head=False,
                         retry=3) -> str:
        """
        执行单线程文件下载，包含进度显示。

        参数:
            url (str): 最终的下载 URL。
            path (str): 输出文件路径。
            headers (Dict[str, str]): HTTP 请求头。
            timeout (int): 请求超时时间。

        返回:
            str: 成功下载后文件的最终路径。

        抛出:
            DownloadError: 如果下载过程中发生错误。
        """
        tmp_path = path + '.single_part'
        downloaded_counter = [0]  # 共享计数器
        lock = threading.Lock()
        logger.info(f"单线程下载开始")
        single_download_start_time = time.perf_counter()

        # 再次 HEAD 请求获取文件大小，确保准确性
        total_size = 0
        if not skip_head:
            try:
                resp_head = self.default_session.head(url, headers=headers, timeout=timeout)
                resp_head.raise_for_status()
                total_size = int(resp_head.headers.get('Content-Length', 0))
                logger.info(f"单线程下载开始。URL: {url}, 总大小: {Downloader._sizeof_fmt_static(total_size)}")
            except requests.exceptions.RequestException as e:
                logger.warning(f"单线程下载获取文件大小失败，可能无法显示总进度: {e}")
                # 即使获取不到总大小，也尝试继续下载

        # monitor = ProgressMonitor(total_size, downloaded_counter, lock)
        # monitor.start()
        # logger.debug("单线程下载的进度监控线程已启动。")

        for _ in range(0, retry):
            try:
                with self.default_session.get(url, headers=headers, stream=True, timeout=timeout) as r:
                    curl = prepared_to_curl(r.request)
                    r.raise_for_status()  # 检查 HTTP 状态码

                    # 确保每次下载前清理旧的临时文件
                    if os.path.exists(tmp_path):
                        logger.warning(f"单线程临时文件 {tmp_path} 已存在，将覆盖。")
                        os.remove(tmp_path)

                    with open(tmp_path, 'wb') as f:
                        for chunk in r.iter_content(8192):
                            if not chunk:
                                continue
                            f.write(chunk)
                            with lock:  # 更新共享计数器
                                downloaded_counter[0] += len(chunk)

                    # monitor.stop()  # 停止进度监控
                    # monitor.join(timeout=5)
                    # if monitor.is_alive():
                    #     logger.warning("单线程下载的进度监控器未能在规定时间内停止。")

                    # 最终文件替换
                    os.replace(tmp_path, path)
                    # logger.info(f"单线程下载成功到: {path}")
                    logger.info(
                        f"单线程下载成功 (总耗时: {time.perf_counter() - single_download_start_time:.4f}秒)")  # <--- 在这里增加结束打点

                    return path
            except requests.exceptions.RequestException as e:
                logger.error(f"单线程下载请求失败: {e}. cURL: {curl}", exc_info=True)
                continue
                # raise DownloadError(f"单线程下载失败: {e}") from e
            except IOError as e:
                logger.critical(f"单线程下载文件写入失败: {e}. 文件: {tmp_path}", exc_info=True)
                continue
                # raise DownloadError(f"单线程下载写入失败: {e}") from e
            except Exception as e:
                logger.critical(f"单线程下载过程中发生未知错误: {e}", exc_info=True)
                continue
                # raise DownloadError(f"单线程下载未知错误: {e} cURL: {curl}") from e
            finally:
                # 无论成功失败，尝试清理临时文件
                self._cleanup_temp_files([tmp_path])
        return path

    def _cleanup_temp_files(self, file_paths: List[str]):
        """
        清理指定的临时文件。
        """
        for fp in file_paths:
            if os.path.exists(fp):
                try:
                    os.remove(fp)
                    logger.debug(f"已清理临时文件: {fp}")
                except OSError as e:
                    logger.warning(f"无法删除临时文件 {fp}: {e}. 请手动清理。", exc_info=True)
