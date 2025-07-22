# downloader.py
"""
HTTP 下载工具，支持进度显示与异常捕获。
"""
import os
import sys
import threading
import time
from typing import Optional, Dict

import requests
from queue import Queue
from PublicMethods.logger import get_logger, setup_log

setup_log()
logger = get_logger(__name__)


class DownloadError(Exception):
    """通用下载错误"""
    pass


class ProgressMonitor(threading.Thread):
    def __init__(self, total_bytes, downloaded_counter, lock, interval=0.01):
        super().__init__(daemon=True)
        self.total = total_bytes
        self.downloaded = downloaded_counter
        self.lock = lock
        self.interval = interval
        self.start_time = time.time()
        # ✅ 用一个独立名字保存退出标志，避免冲突
        self._stop_event = threading.Event()

    def run(self):
        while not self._stop_event.is_set():
            with self.lock:
                dl = self.downloaded[0]
            dl_str = Downloader._sizeof_fmt_static(dl)
            total_str = Downloader._sizeof_fmt_static(self.total)
            sys.stdout.write(f"\r下载进度: {dl_str}/{total_str}")
            sys.stdout.flush()
            time.sleep(self.interval)
        # 最后一次刷新到 100%
        with self.lock:
            dl = self.downloaded[0]
        elapsed = max(time.time() - self.start_time, 0.001)
        speed = dl / elapsed
        dl_str = Downloader._sizeof_fmt_static(dl)
        total_str = Downloader._sizeof_fmt_static(self.total)
        speed_str = Downloader._sizeof_fmt_static(speed) + '/s'
        sys.stdout.write(f"\r下载完成: {dl_str}/{total_str}，平均速度: {speed_str}\n")
        sys.stdout.flush()

    def stop(self):
        """让线程优雅退出（仅设置事件，不在这里 join）"""
        self._stop_event.set()


class SegmentDownloader(threading.Thread):
    """
       分片下载线程类，用于并发下载文件的指定字节区间。

       参数：
           session             requests.Session 对象，用于发起 HTTP 请求
           url                 要下载的资源 URL（最终已处理重定向）
           start_byte (int)    本分片起始字节位置（包含）
           end_byte (int)      本分片结束字节位置（包含）
           tmp_path (str)      本分片临时文件保存路径（.partN）
           queue               Queue 对象，用于将下载结果（start_byte, tmp_path/None）回传给主线程
           headers (dict)      HTTP 请求头，会在此基础上添加 Range 字段
           downloaded_counter  共享的已下载字节计数器（列表或其包装），用于进度统计
           lock                线程锁，用于保护 downloaded_counter 的并发写入
           max_retries (int)   每个分片最大重试次数
    """

    def __init__(self, session, url, start_byte, end_byte, tmp_path, queue,
                 headers, downloaded_counter, lock, max_retries=3, auto_close: bool = False):
        super().__init__()
        self.session = session
        self.auto_close = auto_close
        self.url = url
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.tmp_path = tmp_path
        self.queue = queue
        self.headers = headers.copy()
        self.headers['Range'] = f"bytes={start_byte}-{end_byte}"
        self.max_retries = max_retries
        self.downloaded_ctr = downloaded_counter
        self.lock = lock

    def run(self):
        for attempt in range(1, self.max_retries + 1):
            try:
                with self.session.get(self.url, headers=self.headers, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    with open(self.tmp_path, 'wb') as f:
                        for chunk in r.iter_content(8192):
                            if not chunk:
                                continue
                            f.write(chunk)
                            # 累加到共享计数器
                            with self.lock:
                                self.downloaded_ctr[0] += len(chunk)
                self.queue.put((self.start_byte, self.tmp_path))
                return
            except Exception as e:
                logger.warning(
                    f"分片下载失败 [{self.start_byte}-{self.end_byte}]，重试 {attempt}/{self.max_retries}: {e}"
                )
            finally:
                if self.auto_close:
                    # 关闭独立 session，释放连接池
                    try:
                        self.session.close()
                    except Exception:
                        pass
        # 所有重试失败，放入 None 触发回退逻辑
        self.queue.put((self.start_byte, None))


class Downloader:
    def __init__(self, session=None, threads=4):
        self.threads = threads
        self.session = session or requests.Session()
        self.session2 = requests.Session()

    @staticmethod
    def _sizeof_fmt_static(num, suffix='B'):
        """
        将字节数转换为可读格式，如 1.23MB
        """
        for unit in ['', 'K', 'M', 'G', 'T']:
            if abs(num) < 1024.0:
                return f"{num:.2f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.2f}P{suffix}"

    def _get_final_url(
            self,
            url: str,
            headers: dict = None,
            timeout: int = 15,
            max_redirects: int = 5,
            return_flag: str = None,
    ) -> str:
        """
        force_return: 返回特征，符合特征的直接返回
        手动跟踪 301/302/307 等重定向，返回最终 200 OK 的下载链接。
        如重定向次数超过 max_redirects，则抛出 DownloadError。
        """
        current = url
        for i in range(max_redirects):
            resp = self.session.head(current, headers=headers or {}, timeout=timeout, allow_redirects=False, )
            # 如果是重定向，更新 URL 继续循环
            if resp.status_code in (301, 302, 303, 307, 308) and 'Location' in resp.headers:
                loc = resp.headers['Location']
                if return_flag and return_flag in loc:
                    return loc
                logger.debug(f"[Redirect {i + 1}] {current} → {loc}")
                current = loc
                continue

            # 非重定向状态码，确认无异常后返回
            resp.raise_for_status()
            return current

        raise DownloadError(
            f"超过 {max_redirects} 次重定向仍未拿到资源，最后 URL: {current}"
        )

    def download(
            self,
            url: str,
            path: str,
            headers: Optional[Dict[str, str]] = None,
            timeout: int = 60,
            max_redirects: int = 5,
            multi_session: bool = False,
    ) -> str:
        """
        下载文件，先跟踪重定向，再根据 total(length or 响应头)决定单/多线程下载。
        :param url:    初始 URL（可能先返回 302）
        :param path:   输出文件路径（无 .part）
        :param headers 必须或 length>0，至少提供一种
        """
        headers = headers or {}
        # 先探测最终 URL 与文件大小
        final_url = self._get_final_url(url, headers or {}, timeout, max_redirects)
        resp_head = self.session.head(final_url, headers=headers or {}, timeout=timeout)
        resp_head.raise_for_status()
        total = int(resp_head.headers.get('Content-Length', 0))

        # 共享下载计数和锁
        downloaded_counter = [0]
        lock = threading.Lock()

        # 启动进度监控
        monitor = ProgressMonitor(total, downloaded_counter, lock)
        monitor.start()

        # 分段下载
        part_size = total // self.threads
        queue = Queue()
        tmp_files = []
        threads = []

        logger.info(f"开始下载任务，分片数量：{self.threads}")
        for i in range(self.threads):
            s = i * part_size
            e = (i + 1) * part_size - 1 if i < self.threads - 1 else total - 1
            tmp = f"{path}.part{i}"
            tmp_files.append((s, tmp))

            logger.debug(f"[Downloader] [thread-{i}] range {s}-{e} tmp={tmp}")

            # --- 关键行：决定该分片用哪个 session ---
            if multi_session:
                sess = requests.Session()
                # 若你需要复用代理 / cookie，可简单拷贝：
                sess.trust_env = self.session.trust_env
                sess.headers.update(self.session.headers)  # 可根据实际需求调整
                logger.debug(f"[Downloader] [thread-{i}] new Session() created")
            else:
                sess = self.session

            t = SegmentDownloader(
                session=sess,
                url=final_url,
                start_byte=s,
                end_byte=e,
                tmp_path=tmp,
                queue=queue,
                headers=headers,
                downloaded_counter=downloaded_counter,
                lock=lock,
                auto_close=multi_session  # 让线程在结束时关闭自己的 session
            )
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        # 收集结果并停止监控
        segments = {}
        while not queue.empty():
            s, tmp = queue.get()
            segments[s] = tmp
        monitor.stop()
        monitor.join()

        if any(tmp is None for tmp in segments.values()):
            logger.warning("分段下载失败，回退单线程下载")
            for _, tmp in tmp_files:
                if os.path.exists(tmp):
                    os.remove(tmp)
            return self._single_download(url, path, headers, timeout)

        # 合并分片
        tmp_all = path + ".part"
        with open(tmp_all, 'wb') as outf:
            for s, tmp in sorted(segments.items(), key=lambda kv: kv[0]):
                with open(tmp, 'rb') as inf:
                    outf.write(inf.read())
                os.remove(tmp)
        os.replace(tmp_all, path)
        return path

    def _single_download(self, url, path, headers, timeout):
        """单线程下载也带进度和速度显示"""
        tmp = path + '.part'
        downloaded = 0

        # HEAD 拿总大小（再次确认）
        resp = self.session.head(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        total = int(resp.headers.get('Content-Length', 0))

        start_time = time.time()
        with self.session.get(url, headers=headers, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            with open(tmp, 'wb') as f:
                for chunk in r.iter_content(8192):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)

                    # 计算平均速度
                    elapsed = max(time.time() - start_time, 0.001)
                    speed = downloaded / elapsed

                    dl_str = self._sizeof_fmt_static(downloaded)
                    total_str = self._sizeof_fmt_static(total)
                    speed_str = self._sizeof_fmt_static(speed) + '/s'

                    sys.stdout.write(
                        f"\r下载进度: {dl_str}/{total_str}，平均速度: {speed_str}"
                    )
                    sys.stdout.flush()
        sys.stdout.write("\n")
        os.replace(tmp, path)
        return path
