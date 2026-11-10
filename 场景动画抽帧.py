"""场景动画抽帧（通用版）：把「纯色背景 + 1 个或 2×2 四个物件」的循环视频，抽成像素精灵表
用法：python 场景动画抽帧.py <视频或文件夹> [--grid 2] [--n 12] [--size 128] [--skip 1 3] [--still 1.5] [--out 输出文件夹]
  --grid   1 = 整个画面一个物件；2 = 画面分成 2×2 四格（左上 1、右上 2、左下 3、右下 4）
  --n      取多少帧（视频首尾是同一张图时，整段就是一个循环，均匀取 n 帧）
  --size   每格输出边长（像素，按长边缩放）；0 = 保持视频里的原大小
  --skip   没有动态效果的格子编号，不出动画（例：--skip 1 3）
  --still  动态幅度低于这个百分比也当静止（默认 1.5）
输出（每个物件）：<视频名>_<格号>.png（一行 n 帧）、<视频名>_<格号>_预览.gif、结果.txt
需要：Python 3.9+，pip install opencv-python numpy pillow"""
import argparse, glob, os, sys
import numpy as np, cv2
from PIL import Image
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass
ap = argparse.ArgumentParser(); ap.add_argument('src'); ap.add_argument('--grid', type=int, default=2, choices=(1, 2)); ap.add_argument('--n', type=int, default=12)
ap.add_argument('--size', type=int, default=128); ap.add_argument('--skip', type=int, nargs='*', default=[]); ap.add_argument('--still', type=float, default=1.5); ap.add_argument('--out', default='')
A = ap.parse_args()

def read(path):
    tmp = None; cap = cv2.VideoCapture(path)
    if not cap.isOpened():   # 中文路径打不开时复制到临时英文名再读
        import tempfile, shutil; tmp = os.path.join(tempfile.gettempdir(), 'scene_anim_tmp.mp4'); shutil.copy(path, tmp); cap = cv2.VideoCapture(tmp)
    fr = []
    while True:
        ok, f = cap.read()
        if not ok: break
        fr.append(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
    cap.release()
    if tmp: os.remove(tmp)
    return fr

def keyer(q0):   # 用第 1 帧这一格的四条边估背景色
    b = np.concatenate([q0[:6].reshape(-1, 3), q0[-6:].reshape(-1, 3), q0[:, :6].reshape(-1, 3), q0[:, -6:].reshape(-1, 3)]).astype(float)
    bg = np.median(b, axis=0); spread = np.percentile(np.linalg.norm(b - bg, axis=1), 95); lo, hi = max(40.0, spread * 1.6), max(90.0, spread * 3.0)
    def key(q):
        f = q.astype(float); a = np.clip((np.linalg.norm(f - bg, axis=2) - lo) / (hi - lo), 0, 1)
        m = (a > 0) & (a < 1); f[m] = np.clip((f[m] - bg * (1 - a[m, None])) / np.maximum(a[m, None], 0.35), 0, 255)   # 去溢色
        return np.dstack([f.astype(np.uint8), np.where(a >= 0.47, 255, 0).astype(np.uint8)])
    return key, bg

def run(path):
    name = os.path.splitext(os.path.basename(path))[0]; out = A.out or os.path.join(os.path.dirname(path), '抽帧结果'); os.makedirs(out, exist_ok=True)
    fr = read(path)
    if not fr: print('读不到视频：', path); return []
    H, W = fr[0].shape[:2]; N = len(fr); idx = [int(round(k * (N - 1) / A.n)) for k in range(A.n)]; g = A.grid; QW, QH = W // g, H // g; log = []
    for q in range(g * g):
        no = q + 1; qx, qy = (q % g) * QW, (q // g) * QH
        if no in A.skip: log.append(f'{name} 第 {no} 格：标注没有动态，跳过'); continue
        key, bg = keyer(fr[0][qy:qy + QH, qx:qx + QW]); cells = [key(fr[i][qy:qy + QH, qx:qx + QW]) for i in idx]
        org = cells[0].copy(); oa = org[..., 3] > 0
        if not oa.any(): log.append(f'{name} 第 {no} 格：没找到物件'); continue
        # 去光晕：轮廓外偏背景色的像素删掉；轮廓内被染色、原来不是这个色调的恢复原色（烟雾等灰色不受影响）
        bc = bg - bg.mean(); bc /= np.linalg.norm(bc) + 1e-6
        def tinted(f, nmin=25, cos=0.55):
            f = f.astype(float); ch = f - f.mean(axis=2, keepdims=True); n = np.linalg.norm(ch, axis=2); return ((ch @ bc) / (n + 1e-6) > cos) & (n > nmin)
        ot = tinted(org[..., :3])
        for c in cells:   # 轮廓外很浅的偏色也删（灰烟几乎没有色偏，不受影响）；轮廓内只修明显染色
            c[..., 3][~oa & tinted(c[..., :3], 10, 0.35)] = 0; fix = oa & tinted(c[..., :3]) & ~ot & (c[..., 3] > 0); c[fix] = org[fix]
        # 所有帧的并集包围盒（烟雾飘出去也不裁掉），四周留 4 像素
        ys, xs = np.where(np.any([c[..., 3] > 0 for c in cells], axis=0)); y0, y1, x0, x1 = max(0, ys.min() - 4), min(QH, ys.max() + 5), max(0, xs.min() - 4), min(QW, xs.max() + 5)
        cells = [c[y0:y1, x0:x1] for c in cells]; ch_, cw_ = cells[0].shape[:2]
        if A.size: s = A.size / max(cw_, ch_); sz = (max(1, round(cw_ * s)), max(1, round(ch_ * s)))
        else: sz = (cw_, ch_)
        small = []
        for c in cells:
            im = np.array(Image.fromarray(c).resize(sz, Image.BOX)); im[..., 3] = np.where(im[..., 3] >= 120, 255, 0); small.append(im)
        c0 = small[0].astype(int); op = c0[..., 3] > 0
        mv = max(float(((np.abs(c.astype(int)[..., :3] - c0[..., :3]).max(axis=2) > 24) & op).sum() / max(1, op.sum()) * 100) for c in small[1:])
        base = os.path.join(out, f'{name}_{no}')
        if mv < A.still:
            Image.fromarray(small[0]).save(base + '_静态.png'); log.append(f'{name} 第 {no} 格：动态 {mv:.2f}% 太小，只出静态图'); continue
        Image.fromarray(np.concatenate(small, axis=1)).save(base + '.png')
        S = max(1, 256 // max(sz)); gif = []
        for c in small:
            bgim = Image.new('RGB', (sz[0] * S, sz[1] * S), (58, 88, 64)); im = Image.fromarray(c).resize((sz[0] * S, sz[1] * S), Image.NEAREST); bgim.paste(im, (0, 0), im); gif.append(bgim)
        gif[0].save(base + '_预览.gif', save_all=True, append_images=gif[1:], duration=int(3000 / A.n), loop=0)
        log.append(f'{name} 第 {no} 格：动态 {mv:.1f}%，{A.n} 帧，每格 {sz[0]}×{sz[1]} → {os.path.basename(base)}.png')
    for l in log: print(l)
    with open(os.path.join(out, '结果.txt'), 'a', encoding='utf-8') as f: f.write('\n'.join(log) + '\n')
    return log

paths = sorted(glob.glob(os.path.join(A.src, '*.mp4'))) if os.path.isdir(A.src) else [A.src]
if not paths: print('没找到 mp4：', A.src)
for p in paths: run(p)
