# 信息源清单与调选择器的方法

## 当前清单（4 个）

| # | id | 地址（需实测） | 类型 | 状态 |
|---|---|---|---|---|
| 1 | jwc | https://jwc.xmu.edu.cn/tzgg.htm | 静态列表页 / gbk | 待实测 |
| 2 | gs | https://gs.xmu.edu.cn/tzgg.htm | 静态列表页 | 待实测 |
| 3 | informatics | https://informatics.xmu.edu.cn/tzgg.htm | 静态 / 可能 JS | 待实测 |
| 4 | 待定（团委/图书馆/就业） | — | 优先找 RSS | 待定 |

> 上表地址只是**初始猜测**。第一件事是打开浏览器逐条核实栏目路径（`tzgg.htm` / `tzgg/` / `index.htm` 都可能）。

## 怎么调选择器（10 分钟一个源）

1. 浏览器打开列表页，`Ctrl+U` 看源码：能直接看到标题文字 → 服务端渲染，`selectolax` 够用；
2. `F12` → 检查一条新闻 → 右键「复制 → 复制选择器」，取到能圈住**整行**的那层（通常是 `ul.news_list > li`）；
3. 填进 `svc/config/sources.yaml` 的 `item_selector`；
4. 跑一次看结果：

```powershell
curl -X POST "http://127.0.0.1:8000/api/admin/crawl" -H "X-Admin-Token: change-me"
curl "http://127.0.0.1:8000/api/digest?limit=20"
```

5. 判定标准：标题与浏览器里一致、无乱码、无「更多>>」「[详情]」这类噪声。

## 常见坑

| 现象 | 原因 | 处理 |
|---|---|---|
| 标题全问号 | 编码猜错 | `encoding: gbk` 或 `auto` |
| 抓到一堆导航链接 | 选择器太宽 | 换到能圈住整行的那层 |
| 只有标题没有正文 | 详情页结构不同 | 配 `content_selector`，或留空用通用抽取 |
| 内容在 PDF 附件里 | 正文是文件 | 本版跳过（V2 用 pypdf） |
| 需要登录 | 教务系统 | 不做，写进报告「范围外」 |
| 页面是 JS 渲染 | 源码里没有内容 | F12 找内部 JSON 接口；没有就 Playwright（V2） |

## 合规

- 每源每小时 1 次、单源串行、随机延迟 1~3 秒；
- 遵守 robots.txt；只抓公开页面；
- 只存标题、摘要、时间、链接，不镜像正文。
