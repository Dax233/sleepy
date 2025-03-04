Set ws = CreateObject("Wscript.Shell")
' 激活conda环境
ws.run "cmd.exe /c conda activate sleepy && python %UserProfile%\win_device.py", vbhide
