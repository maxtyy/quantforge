# 本次验证记录

环境：Python 3.12.3，Linux；依赖版本见 `requirements.lock.txt`。

- `pytest -q`：35 项测试通过。第三方 Starlette 测试客户端提示未来改用 httpx2，当前测试正常。
- `ruff check .` 和 `ruff format --check .`：通过。
- `quantforge demo`：756 行合成日线完成回测，导出权益、成交、JSON 报告与输入行情。
- `python -m build`：源码包和 wheel 构建成功，包含网页静态资源。
- Chromium 浏览器：默认回测、切换策略、JSON 下载、模拟买入卖出、CSV 上传与回测均通过，无 JavaScript 异常。
- 1440 像素桌面和 390 像素手机布局检查通过；修复了窄屏表格造成的整页横向溢出。
- Yahoo 真实网络下载尝试返回上游限流 `YFRateLimitError`，因此本环境未验证成功下载真实行情；CLI 返回清晰错误，CSV 与离线演示链路已验证。

GitHub Actions 已配置 Python 3.11、3.12、3.13；本记录不代表这些云端任务已经执行。远程仓库尚待 GitHub 账号登录后创建。
