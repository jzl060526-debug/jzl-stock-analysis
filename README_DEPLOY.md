# JZL Stock Analysis - Streamlit Deploy Package

这是从本地版 JZL证券分析 项目整理出的云端部署包。

## 部署入口

Streamlit Cloud 主文件：

```text
app.py
```

## 推荐部署方式

1. 在 GitHub 新建仓库，例如：`jzl-stock-analysis`
2. 上传本文件夹内所有文件到仓库根目录
3. 打开 Streamlit Community Cloud
4. New app / Create app
5. Repository 选择你的 GitHub 仓库
6. Branch 选择 `main`
7. Main file path 填：`app.py`
8. Deploy

## API Key

不要把 API Key 写进代码或上传 GitHub。
在 Streamlit Cloud 的 App settings / Secrets 中配置：

```toml
DEEPSEEK_API_KEY = "sk-你的key"
OPENAI_API_KEY = "sk-你的key"
```

没有 Key 时，普通行情、扫描、回测页面仍可尝试使用；AI 相关页面会提示缺少 Key。

## 已从公开部署包移除的内容

- 本地行情数据库 `data/market_data.sqlite`
- 本地行情缓存 `data_cache/*.csv`
- 日志、输出、报告文件
- 个人交易记录内容
- Windows BAT 启动脚本
- `__pycache__`

## 注意

这是公开展示包，不等同于你的完整本地工作台备份。真实交易记录、API Key、个人日志不要上传到公开仓库。
