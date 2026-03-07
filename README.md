# OpenResume

OpenResume 是一个面向 Windows 的桌面应用，用简历驱动职位搜索、匹配分析和用户主导的引导投递。开源主线明确不提供自动提交、隐身伪装、验证码绕过或其他对抗风控能力。

## 技术栈

- Electron 桌面壳
- React + Vite + TypeScript 前端界面
- FastAPI + SQLModel + SQLite 本地接口服务
- 可选的 Playwright 专用浏览器会话能力

## 产品边界

- `recommend_only`：只搜索、匹配、排序职位
- `review_in_browser`：打开职位页面，由用户自行查看
- `guided_apply`：进入投递流程并尽量预填信息，但最终提交始终由用户亲自点击

## 本地开发

### 前端 + Electron

Windows PowerShell 下建议使用 `npm.cmd`：

```bash
npm.cmd install
npm.cmd run dev
```

### 后端

```bash
cd backend
python -m pip install -e .[dev]
```

开发模式下，Electron 会自动尝试用 `python -m openresume_api` 拉起本地后端。

## 常用检查

```bash
cd backend
python -m pytest
```

```bash
cd ..
npm.cmd run typecheck
npm.cmd run build
```

## Windows 打包说明

仓库已经包含 Electron 桌面壳和适合 PyInstaller 的后端入口。要生成可分发的 Windows 安装包，还需要先把 Python 后端打成可执行文件，再交给 Electron Builder 打包。

### 1. 生成后端可执行文件

```bash
cd backend
python -m pip install -e .[packaging]
pyinstaller --onefile --name openresume-api openresume_api/__main__.py
```

### 2. 打包桌面端

```bash
cd ..
npm.cmd run package:windows
```

如果缺少 `backend/dist/openresume-api.exe`，打包脚本会直接报错并提示先执行上面的后端打包步骤。
