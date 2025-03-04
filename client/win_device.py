# coding: utf-8
'''
win_device.py
在 Windows 上获取窗口名称
by: @wyf9, @pwnint, @kmizmal
依赖: pywin32, requests
'''

# ----- Part: Import

import sys
import io
from time import sleep
import time  # 改用 time 模块以获取更精确的时间
from datetime import datetime
from requests import post
import threading
import win32api  # type: ignore - 勿删，用于强忽略非 windows 系统上 vscode 找不到模块的警告
import win32con  # type: ignore
import win32gui  # type: ignore
from pywintypes import error as pywinerror # type: ignore

# ----- Part: Config

# --- config start
# 服务地址, 末尾同样不带 /
SERVER: str = 'http://localhost:9010'
# 密钥
SECRET: str = 'wyf9test'
# 设备标识符，唯一 (它也会被包含在 api 返回中, 不要包含敏感数据)
DEVICE_ID: str = 'device-1'
# 前台显示名称
DEVICE_SHOW_NAME: str = 'MyDevice1'
# 检查间隔，以秒为单位
CHECK_INTERVAL: int = 2
# 是否忽略重复请求，即窗口未改变时不发送请求
BYPASS_SAME_REQUEST: bool = True
# 控制台输出所用编码，避免编码出错，可选 utf-8 或 gb18030
ENCODING: str = 'gb18030'
# 当窗口标题为其中任意一项时将不更新
SKIPPED_NAMES: list = ['', '系统托盘溢出窗口。', '新通知', '任务切换', '快速设置', '通知中心', '搜索', 'Flow.Launcher', '任务视图', '任务切换', 'Snipper - Snipaste']
# 当窗口标题为其中任意一项时视为未在使用
NOT_USING_NAMES: list = ['我们喜欢这张图片，因此我们将它与你共享。', '启动']
# 是否反转窗口标题，以此让应用名显示在最前 (以 ` - ` 分隔)
REVERSE_APP_NAME: bool = False
# 鼠标静止判定时间 (分钟)
MOUSE_IDLE_TIME: int = 15
# 鼠标移动检测的最小距离 (像素)
MOUSE_MOVE_THRESHOLD: int = 10
# 控制日志是否显示更多信息
DEBUG: bool = True
# 代理地址 (<http/socks>://host:port), 设置为空字符串禁用
PROXY: str = ''
# --- config end

# ----- Part: Functions

# stdout = TextIOWrapper(stdout.buffer, encoding=ENCODING)  # https://stackoverflow.com/a/3218048/28091753
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_print_ = print


def print(msg: str, print_only: bool = False, **kwargs):
    '''
    修改后的 `print()` 函数，解决不刷新日志的问题
    原: `_print_()`
    '''
    msg = str(msg).replace('\u200b', '')
    try:
        if print_only:
            _print_(msg, flush=True, **kwargs)
        else:
            _print_(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {msg}', flush=True, **kwargs)
    except Exception as e:
        _print_(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] Log Error: {e}', flush=True)


def debug(msg: str, **kwargs):
    '''
    显示调试消息
    '''
    if DEBUG:
        print(msg, **kwargs)


def reverse_app_name(name: str) -> str:
    '''
    反转应用名称 (将末尾的应用名提前)
    如 Before: win_device.py - dev - Visual Studio Code
    After: Visual Studio Code - dev - win_device.py
    '''
    lst = name.split(' - ')
    new = []
    for i in lst:
        new = [i] + new
    return ' - '.join(new)


# ----- Part: Send status

Url = f'{SERVER}/device/set'
last_window = ''


def send_status(using: bool = True, app_name: str = '', **kwargs):
    '''
    post 发送设备状态信息
    设置了 headers 和 proxies
    '''
    json_data = {
        'secret': SECRET,
        'id': DEVICE_ID,
        'show_name': DEVICE_SHOW_NAME,
        'using': using,
        'app_name': app_name
    }
    if PROXY:
        return post(
            url=Url,
            json=json_data,
            headers={
                'Content-Type': 'application/json'
            },
            proxies={
                'all': PROXY
            },
            **kwargs
        )
    else:
        return post(
            url=Url,
            json=json_data,
            headers={
                'Content-Type': 'application/json'
            },
            **kwargs
        )

# ----- Part: Shutdown handler


def on_shutdown(hwnd, msg, wparam, lparam):
    '''
    关机监听回调
    '''
    if msg == win32con.WM_QUERYENDSESSION:
        print("Received logout event, sending not using...")
        try:
            resp = send_status(
                using=False,
                app_name="要关机了喵"
            )
            debug(f'Response: {resp.status_code} - {resp.json()}')
            if resp.status_code != 200:
                print(f'Error! Response: {resp.status_code} - {resp.json()}')
        except Exception as e:
            print(f'Exception: {e}')
        return True  # 允许关机或注销
    return 0  # 其他消息


# 注册窗口类
wc = win32gui.WNDCLASS()
wc.lpfnWndProc = on_shutdown  # 设置回调函数
wc.lpszClassName = "ShutdownListener"
wc.hInstance = win32api.GetModuleHandle(None)

# 创建窗口类并注册
class_atom = win32gui.RegisterClass(wc)

# 创建窗口
hwnd = win32gui.CreateWindow(
    class_atom,  # className
    "Sleepy Shutdown Listener",  # windowTitle
    0,  # style
    0,  # x
    0,  # y
    0,  # width
    0,  # height
    0,  # parent
    0,  # menu
    wc.hInstance,  # hinstance
    None  # reserved
)


def message_loop():
    '''
    (需异步执行) 用于在后台启动消息循环
    '''
    win32gui.PumpMessages()


# 创建并启动线程
message_thread = threading.Thread(target=message_loop, daemon=True)
message_thread.start()

# ----- Part: Mouse idle

# 鼠标状态相关变量
last_mouse_pos = win32api.GetCursorPos()
last_mouse_move_time = time.time()
is_mouse_idle = False
cached_window_title = ''  # 缓存窗口标题, 用于恢复


def check_mouse_idle() -> bool:
    '''
    检查鼠标是否静止
    返回 True 表示鼠标静止超时
    '''
    global last_mouse_pos, last_mouse_move_time, is_mouse_idle

    try:
        current_pos = win32api.GetCursorPos()
    except pywinerror as e:
        print(f'Check mouse pos error: {e}')
        return None
    current_time = time.time()

    # 计算鼠标移动距离
    dx = abs(current_pos[0] - last_mouse_pos[0])
    dy = abs(current_pos[1] - last_mouse_pos[1])
    distance = (dx * dx + dy * dy) ** 0.5

    # 打印详细的鼠标状态信息
    debug(f'Mouse: current={current_pos}, last={last_mouse_pos}, distance={distance:.1f}px')

    # 如果移动距离超过阈值
    if distance > MOUSE_MOVE_THRESHOLD:
        last_mouse_pos = current_pos
        last_mouse_move_time = current_time
        if is_mouse_idle:
            is_mouse_idle = False
            print(f'Mouse wake up: moved {distance:.1f}px > {MOUSE_MOVE_THRESHOLD}px')
        else:
            debug(f'Mouse moving: {distance:.1f}px > {MOUSE_MOVE_THRESHOLD}px')
        return False

    # 检查是否超过静止时间
    idle_time = current_time - last_mouse_move_time
    debug(f'Idle time: {idle_time:.1f}s / {MOUSE_IDLE_TIME*60:.1f}s')

    if idle_time > MOUSE_IDLE_TIME * 60:
        if not is_mouse_idle:
            is_mouse_idle = True
            print(f'Mouse entered idle state after {idle_time/60:.1f} minutes')
        return True

    return is_mouse_idle  # 保持当前状态

# ----- Part: Main interval check


def do_update():
    global last_window, cached_window_title, is_mouse_idle

    # 获取当前窗口标题和鼠标状态
    current_window = win32gui.GetWindowText(win32gui.GetForegroundWindow())
    mouse_idle = check_mouse_idle()
    debug(f'--- Window: `{current_window}`, mouse_idle: {mouse_idle}')

    # 始终保持同步的状态变量
    window = current_window
    using = True

    # 鼠标空闲状态处理（优先级最高）
    if mouse_idle:
        # 缓存非空闲时的窗口标题
        if not is_mouse_idle:
            cached_window_title = current_window
            print('Caching window title before idle')
        # 设置空闲状态
        using = False
        window = ''
        is_mouse_idle = True
    else:
        # 从空闲恢复
        if is_mouse_idle:
            window = cached_window_title
            using = True
            is_mouse_idle = False
            print('Restoring window title from idle')

    # 是否需要发送更新
    should_update = (
        mouse_idle != is_mouse_idle or  # 鼠标状态改变
        window != last_window or  # 窗口改变
        not BYPASS_SAME_REQUEST  # 强制更新模式
    )

    if should_update:
        # 窗口名称检查 (未使用列表)
        if current_window in NOT_USING_NAMES:
            using = False
            debug(f'* not using: `{current_window}`')

        # 窗口名称检测 (跳过列表)
        if current_window in SKIPPED_NAMES:
            debug(f'* in skip list: `{current_window}`, ', end='')
            if mouse_idle == is_mouse_idle:
                # 鼠标状态未改变 -> 直接跳过
                print('skipped', print_only=True)
                return
            else:
                # 鼠标状态改变 -> 将窗口名称设为上次 (非未在使用) 的名称
                print(f'set app name to last window: `{last_window}`', print_only=True)
                window = last_window

        # 发送状态更新
        print(f'Sending update: using = {using}, app_name = "{window}", idle = {mouse_idle}')
        try:
            resp = send_status(
                using=using,
                app_name=window
            )
            debug(f'Response: {resp.status_code} - {resp.json()}')
            if resp.status_code != 200 and not DEBUG:
                print(f'Error! Response: {resp.status_code} - {resp.json()}')         
            stat = 0
            if using == False:
                stat = 1
            resp = get(f'{SERVER}/set?secret={SECRET}&status={stat}')
            print(f'[/set] Response: {resp.status_code} - {resp.json()}')
            last_window = window
        except Exception as e:
            print(f'Error: {e}')
    else:
        debug('No state change, skipping update')
        return


def main():
    while True:
        do_update()
        sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, SystemExit) as e:
        # 如果中断或被 taskkill 则发送未在使用
        debug(f'Interrupt: {e}')
        try:
            resp = send_status(
                using=False,
                app_name=f'Client Exited: {e}'
            )
            debug(f'Response: {resp.status_code} - {resp.json()}')
            if resp.status_code != 200:
                print(f'Error! Response: {resp.status_code} - {resp.json()}')
        except Exception as e:
            print(f'Exception: {e}')
