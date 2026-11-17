# 信息源清单与实测结论

> 实测时间：2026-11-17。工具：`scripts/probe_source.py`（探路径与编码）、`scripts/list_structure.py`（看列表结构、推选择器）。
> 结论会变——厦大站点改版后要重跑这两个脚本。

## 一、当前 4 个源

| # | id | 源 | 地址 | 渲染方式 | item_selector | 状态 |
|---|---|---|---|---|---|---|
| 1 | `jwc` | 教务处 | https://jwc.xmu.edu.cn/tzgg.htm | 服务端 | `li.news`（15 条） | ✅ 可直接抓 |
| 2 | `tw` | 校团委 | https://tw.xmu.edu.cn/tzgg.htm | 服务端 | `div.col-md-9.col-sm-9.col-xs-9`（15 条） | ✅ 可直接抓 |
| 3 | `xaxq` | 翔安校区 | https://xaxq.xmu.edu.cn/xqdt/tzgg.htm | 服务端 | `div.news-list-title`（15 条） | ✅ 可直接抓 |
| 4 | `informatics` | 信息学院 | https://informatics.xmu.edu.cn/news_events/tzgg.htm | **Vue 动态** | —— | ❌ 静态抓不到 |

## 二、信息学院为什么抓不到（实测记录）

1. `https://informatics.xmu.edu.cn/tzgg.htm` → **HTTP 404**（会跳到首页，就是你看到的现象）；
2. 首页真正的「通知公告」入口有两个：`/xszx/announces.htm`（学生中心）和 `/news_events/tzgg.htm`（查看更多）；
3. 这两个页面**都是空壳**：
   - 137 个 `<a>` 全是导航（首页/学院概况/…），**0 条文章链接**；
   - `wbnewsid` 出现 0 次（WebPlus 的文章 ID 标记），说明文章列表没渲染进 HTML；
   - 页面引了 `vue.js` + `axios.js`，列表由前端请求后填充。
4. 站内唯一能看到服务端渲染的栏目是「外事公示」（`list.jsp?...&wbtreeid=2481`），但那是教师出国公示，对学生没用。

**判定：T2（需要浏览器渲染）。** MVP 阶段不值得为它引入 Playwright，先留空。

## 三、信息学院的三个选项（按推荐顺序）

| 方案 | 做法 | 代价 | 建议 |
|---|---|---|---|
| A. 先换源 | 用翔安校区顶上（已配置好），学院通知等 V2 | 0 | **当前采用** |
| B. Playwright | 起一个 `playwright` 容器，每轮渲染一次列表 | +1 容器、~300MB 浏览器、每轮 3~8 秒 | V2 第一项 |
| C. 扒 Vue 的 axios 接口 | 从页面 JS 里找请求地址，直接拿 JSON | 接口无文档、随时变 | 不推荐 |

## 四、怎么自己核一个新源（团队自查用）

```powershell
# 1) 探路径与编码：会列出页面里所有「通知/公告」类入口
python scripts\probe_source.py https://xxx.xmu.edu.cn/ --try=tzgg.htm,tzgg/,xwdt.htm

# 2) 看列表结构：给出最可能的选择器与样例标题
python scripts\list_structure.py https://xxx.xmu.edu.cn/tzgg.htm
```

判定标准：**`list_structure.py` 报出「命中 ≥10 条」且样例标题正常 → 可用**。
若报「链接总数很多、像标题的 0 条」，基本就是 JS 渲染，按 T2 处理。

## 五、合规

- 每源每小时 1 次、单源串行、随机延迟 1~3 秒；
- 遵守 robots.txt；只抓公开页面；
- 只存标题、摘要、时间、链接，不镜像正文。
