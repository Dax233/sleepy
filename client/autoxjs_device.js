/*
autoxjs_device.js
使用 Autox.js 编写的安卓自动更新状态脚本
by wyf9. all rights reserved. (?)
Co-authored-by: NyaOH-Nahida - 新增捕捉退出事件，将退出脚本状态上报到服务器。
*/

// config start
const API_URL = 'https://sleepy.wyf9.top/device/set'; // 你的完整 API 地址，以 `/device/set` 结尾
const SET_API_URL = 'https://sleepy.wyf9.top/set';
const SECRET = '绝对猜不出来的密码'; // 你的 secret
const ID = 'a-device'; // 你的设备 id, 唯一
const SHOW_NAME = '一个设备'; // 你的设备名称, 将显示在网页上
const CHECK_INTERVAL = '3000'; // 检查间隔 (毫秒, 1000ms=1s)
const SKIPPED_NAMES = ['系统界面', '系统界面组件', '手机管家', '平板管家', 'System UI', 'Security tools'] // 获取到的软件名包含列表中之一时忽略
// config end

auto.waitFor(); // 等待无障碍

// 替换了 secret 的日志, 同时添加前缀
function log(msg) {
    try {
        console.log(`[sleepyc] ${msg.replace(SECRET, '[REPLACED]')}`);
    } catch (e) {
        console.log(`[sleepyc] ${msg}`);
    }
}
function error(msg) {
    try {
        console.error(msg.replace(SECRET, '[REPLACED]'));
    } catch (e) {
        console.error(msg);
    }
}

var last_status = '';
var times = 0;

function check_status() {
    /*
    检查状态并返回 app_name (如 未亮屏/获取不到应用名 则返回空)
    [Tip] 如有调试需要可自行取消 log 注释
    */
    // log(`[check] screen status: ${device.isScreenOn()}`);
    if (!device.isScreenOn()) {
        return ('');
    }
    var app_package = currentPackage(); // 应用包名
    // log(`[check] app_package: '${app_package}'`);
    var app_name = app.getAppName(app_package); // 应用名称
    // log(`[check] app_name: '${app_name}'`);
    var battery = device.getBattery(); // 电池百分比
    // log(`[check] battery: ${battery}%`);
    // 判断设备充电状态
    if (device.isCharging()) {
        var retname = `[${battery}% +] ${app_name}`;
    } else {
        var retname = `[${battery}%] ${app_name}`;
    }
    if (!app_name) {
        retname = '';
    }
    return (retname);
}
function send_status() {
    /*
    发送 check_status() 的返回
    */
    var app_name = check_status();
    log(`ret app_name: '${app_name}'`);

    // 判断是否与上次相同
    if (app_name == last_status) {
        times = parseInt(times) + 1;
        log(`same as last status, times: ${times}`);
        if (times >= 200) {
            log('times reached 200, resetting app_name and times');
            handing = true;
        } else {
            log('same as last status, bypass request');
            return;
        }
    } else {
        times = 0;
        handing = false;
        log('status changed, reset times to 0');
    }


    // 判断是否在忽略列表中
    for (let i = 0; i < SKIPPED_NAMES.length; i++) {
        if (app_name.includes(SKIPPED_NAMES[i])) {
            log(`bypass because of: '${SKIPPED_NAMES[i]}'`);
            return;
        }
    }

    // 请求在线设备情况
    var otherUsing = false;
    try {
        var response = http.get("https://miraiseori-sleepy.hf.space/query");
        if (response.statusCode == 200) {
            var data = JSON.parse(response.body.string());
            if (data.success) {
                var devices = data.device;
                for (var device_id in devices) {
                    if (device_id == ID) {
                        continue;
                    }
                    var device_info = devices[device_id];
                    var using = device_info.using;
                    if (using) {
                        otherUsing = true;
                        var device_name = device_info.show_name || "未知设备";
                        log(`${device_name} is in using.`);
                    }
                }
            }
        }
    } catch (e) {
        otherUsing = false;
        log(`Error! otherUsing False! ${e}`);
    }
    
    last_status = app_name;
    // 判断 using
    if (app_name == '') {
        log('using: false');
        var using = false;
        stas = 1
    } else {
        log('using: true');
        var using = true;
        stas = 0
    }
    if (otherUsing) {
        log('other device is using, setting using to True');
        using = true;
        stas = 0;
    }

    if (handing) {
        log('handing: true');
        if (times >= 201) {
            log('bypass because of handing');
            return ;
        }
        using = false;
        stas = 1;
    }

    // POST to api
    log(`Status string: '${app_name}'`);
    log(`POST ${API_URL}`);
    r = http.postJson(API_URL, {
        'secret': SECRET,
        'id': ID,
        'show_name': SHOW_NAME,
        'using': using,
        'app_name': app_name
    });
    log(`response: ${r.body.string()}`);
    if (app_name = 'spacedesk') {
        log(`[sleepy] Appname is spacedesk, unset status.`);
        return;
    }
    log(`GET ${SET_API_URL}`);
    resp = http.get(`${SET_API_URL}?secret=${SECRET}&status=${stas}`);
    log(`[/set] Response: ${resp.status} - ${resp.body.string()}`);
}


// 程序退出后上报停止事件
events.on("exit", function () {
    log("Script exits, uploading using = false");
    toast("[sleepy] 脚本已停止, 上报中");
    // POST to api
    log(`POST ${API_URL}`);
    try {
        r = http.postJson(API_URL, {
            'secret': SECRET,
            'id': ID,
            'show_name': SHOW_NAME,
            'using': false,
            'app_name': '[Client Exited]' // using 为 false 时前端不会显示这个, 而是 '未在使用'
        });
        log(`response: ${r.body.string()}`);
        toast("[sleepy] 上报成功");
    } catch (e) {
        error(`Error when uploading: ${e}`);
        toast(`[sleepy] 上报失败! 请检查控制台日志`);
    }
});

while (true) {
    log('---------- Run\n');
    try {
        send_status();
    } catch (e) {
        error(`ERROR sending status: ${e}`);
    }
    sleep(CHECK_INTERVAL);
}
