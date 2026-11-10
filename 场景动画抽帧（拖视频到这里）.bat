@echo off
chcp 65001 >nul
rem 把一个或多个 mp4（或装视频的文件夹）拖到这个文件上；默认 2×2 四格、12 帧、每格 128 像素
cd /d "%~dp0"
set PY=python
where python >nul 2>nul || set PY=py
for %%F in (%*) do %PY% "场景动画抽帧.py" "%%~F" --grid 2 --n 12 --size 128
echo.
echo 完成，结果在视频旁边的「抽帧结果」文件夹里。没有反应请先安装 Python，并执行 pip install opencv-python numpy pillow
pause
