# 清渠排水调查交班

早班测绘员整理调查和沟涵登记。值班员对冻结修订在线核对公开起点，再按幅发行固定件。夜班登记来件，断开源目录后点名使用完整同版实收组合。巡查员用排口距离或入环距离与环长安排复查。次班可以勘误重发，也可以按旧报告号核对当时所用实收件。

## 运行

使用 Python 3.11 标准库和 SQLite。从项目根目录执行下列命令。

```text
python3 -B verify.py
python3 -B demo.py
```

`check_project.py` 由运行环境提供，加载 `tests` 包的完整回归。`verify.py` 在同一入口内运行原回归与 `reuse_cases.py` 的复用核验，任一业务断言失败即以非零退出。演示在临时目录通过正式接口冻结、发行、补发、实收，并在停源后用旧幅加复用声明签报目标修订。它在关闭源站连接后移走源目录，核对隔离报告并重开中心存储复领。

## 登记和计算

调查输入为 JSON 对象，包含这六个字段。

| 字段 | 记录格式 |
| --- | --- |
| `survey` | 调查号字符串 |
| `pieces` | 非空且无重名的声明幅名数组，可声明本次不经过的幅 |
| `cells` | `[格号, 幅名, 是否有效]` 记录数组，有效状态用 JSON 布尔值 |
| `links` | `[起格, 后继格]` 有向登记数组 |
| `starts` | `[公开起点名, 格号]` 记录数组 |
| `outlets` | `[排口号, 格号]` 记录数组 |

标识使用非空字符串，不含首尾空白和控制字符 U+0000 至 U+001F。格号在调查内唯一，起点名和排口号在各自类别内唯一。每个有效非排口格恰有一个有效后继。排口格无后继，每格最多登记一个排口号。缺测格仍归属一个声明幅，不能作接续任一端、起点或排口。起点可以登记在排口上。

起点计第 0 跳。每次移动计 1 跳，跨幅移动同样计 1 跳。排口结果记为 `{"kind":"outlet","outlet":"O","hops":4}`。循环结果记为 `{"kind":"loop","entry_hops":1,"loop_length":3}`。若首个重复位置在第 i、j 跳到达，入环为 i，环长为 j−i。多次进同一幅并不等同于重访同一位置。结果不受幅件顺序、收件顺序和存储编号影响。

## Python 接口

给源站创建可写目录，再以其中的 SQLite 路径构造 `survey.revision_store.RevisionStore` 和 `issue.catalog.IssueCatalog`。给中心另建 SQLite 路径，以该同一路径构造 `receipt.inventory.ReceiptInventory` 和 `reports.store.ReportStore`。首次使用各存储前调用 `initialize()`。可在重开后再次调用，原修订、固定件、实收和稿执继续可用。

| 入口 | 输入与成功返回 |
| --- | --- |
| `survey.intake.parse_survey(data)` | 解析登记对象为可编辑 `SurveyDraft`，各登记表为列表 |
| `survey.revisions.freeze(revisions, registration)` | 接收登记对象或工作稿，校验全图、保存独立快照，返回修订号字符串 |
| `survey.reference.online(revisions, revision_id, start)` | 返回 `OutletOutcome` 或 `LoopOutcome`，可用 `as_record()` 取得字典 |
| `issue.catalog.issue(revisions, catalog, revision_id, piece)` | 返回 `IssuedPiece`，含 `issue_id` 和 `raw` 原字节，同版同幅重复发行复用固定件 |
| `issue.catalog.issue(None, catalog, issue_id=original_id)` | 按发行号返回完整原件 |
| `receipt.intake.receive(inventory, raw)` | 校验 V1 幅件并以原字节实收，返回整数实收号 |
| `issue.catalog.compatibility_for(revisions, catalog, old_issue_id, target_revision)` | 发行站判定已固定旧幅对另一冻结修订是否可复用，返回复用声明字节 |
| `review.assessment.review(inventory, reports, survey, revision_id, receipt_ids, start)` | 只用点名来件核定并签存，返回 `ReportBundle` |
| `review.assessment.review_reuse(inventory, reports, survey, target_revision, receipt_ids, declarations, start)` | 停源后凭点名原件与复用声明，按目标修订接通并签存 |
| `reports.history.read(reports, report_id)` | 按整数报告号读取此前提交的 `ReportBundle` |

`ReportBundle` 含 `report_id`、报告 JSON 原字节 `report`、按幅排序的 `(幅名, 实收号)` 元组 `provenance` 和首执 JSON 原字节 `first_receipt`。报告保存调查、修订、起点和互斥结论。首执保存报告号、报告字节的 SHA-256 和逐幅实收号。新修订和新报告不会改写已签记录。

无效参数、无效工作稿、坏件、同号异件、缺幅、混调查或修订、同幅资料歧义、未知起点和无法解析的接续用 `ValueError` 拒绝。查询未知修订、发行、实收或报告号抛出 `KeyError`。持久化失败保留 SQLite 异常。相同原件重投返回其原实收号，复核中重复点名同一实收号只计算一次覆盖。写入或提交失败时报告、出处和首执共同回滚。

## 固定幅件

V1 外层是 UTF-8 JSON，`version` 为整数 1，`issue_id` 为发行号，`body` 为 JSON 正文字符串，`sha256` 为该字符串 UTF-8 字节的 SHA-256 小写十六进制摘要。摘要用于校验传输完整性。实收账保存收到的完整外层字节。

正文含 `survey`、`revision`、`piece`、`coverage`、`starts`、`incoming`、`routes` 和 `joins`。`starts` 从公开点名索引本幅路线。`incoming` 从入幅口索引 `from_piece` 与本幅 `route`。同一来幅进入同一格的接续共用一个口。幅内路线可指向排口、局部环或下一幅的入幅口。过缝路线的 `hops` 已含跨缝的那一步。`joins` 记录同幅、同出幅口的两条路线在幅内第一次同位的双侧偏移，格式为 `[较小路线号, 较大路线号, 左偏移, 右偏移]`。路线号与口号只在固定修订的交接中使用。原格网及私有格号留在源站。

中心用所选来件核对同版和完整幅集，包含本次不经过的声明幅。随后解析起点和过缝接续，按实际访问顺序计算终局。正式报告的出处只记录本次选中的固定实收号。

## 勘误后复用

`issue.catalog.compatibility_for` 只能在源站在线时调用：它同时加载旧件所属修订和目标修订的冻结格网，按公开起点点名、按（来幅、目的幅、目的格）登记身份对应真实入幅口，逐路线核对排口号与跳数、入环跳数与环长、跨幅真实目的口与跳数，以及同出幅口路线的首次汇合是否存在和双侧偏移。等价时出具版本 2 的声明信封，外层含 `version`、`body`、`sha256`，沿用 V1 的传输完整性边界；正文绑定调查、幅名、旧发行号、旧件完整字节 SHA-256、旧修订与确切目标修订，并携带目标版口号下的 `starts`、`inlets`、`seams` 和原 `joins`，足以离线解释接缝。私有格号不进入声明。

`review.assessment.review_reuse` 在停源后工作。每个目标幅恰用一件实收件：同版件无需声明，异版件须有恰好一份绑定该原件与本次目标的声明，所有传入声明都须用到。中心从原件取得本地路线和汇合依据，按声明的目标版口号接通跨幅路线，终局口径与同版复核一致。新入口的报告沿用 `revision` 记录目标修订，并新增 `sources`（幅名到实收号）和 `reuse_declarations`（复用幅名到所用声明完整字节 SHA-256）；首执保留 `report_sha256` 与 `sources` 并增加同样的声明摘要映射。同版选件可走原 `review`，也可走新入口并传入空声明列表，此时报告带空的 `reuse_declarations`。任何缺幅、歧义、错绑、损坏声明、接缝不通或提交失败均拒绝，且无新报告、出处或首执落账。

## 样例和回归

`samples/early.json` 与 `samples/control.json` 均包含两幅。由 S 观察，两版的公开分段跳数依次为 2、1、2。前者在第 1 和第 4 跳到达同一幅内位置，后者在第 2 和第 5 跳重访入幅口，两版环长均为 3。两版另有由 T 两次过缝后抵达 O 的路线，手算为 4 跳。

`tests/test_prepare.py` 验证冻结和补发、缺测格与无登记终端拒绝。`tests/test_receipt.py` 验证来件完整性、冲突、同幅唯一和完整同版选件。`tests/test_review.py` 验证手算排口和循环、断源用件、独立合法幅件与接续错误。`tests/test_reports.py` 验证写入边界及 SQLite 提交失败、勘误和历史出处。`tests/test_initialize.py` 在保留用户勘误和两份稿执的情况下重复初始化并核对实存结果。
