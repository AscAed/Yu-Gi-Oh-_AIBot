# 本机环境与资产审计

2026-10-30静态核对的历史基线为`main / d3bc212`；旧普通包CLI/worker哈希与清单一致、主要配置路径存在，当时未运行程序。2026-10-31普通包及赛事冻结配置doctor在`main / a8d6356`源码时点分别返回ready；随后文档与CI触发范围更新随PR #14合入`main / 4869393`，合并检查全绿。PR #14未重建或切换部署资产，因此这些doctor结果不代表当前源码已部署。P4-R5最新源码双资产发布验收仍开放。此前`8315232`为W1设计阶段历史基线，见[W1-A后路线](superpowers/plans/2026-10-30-post-w1a-project-route.md)。

原目录体积审计日期：2026-10-19；这些数值会随实验和构建变化。2026-10-27自检分别对普通包和赛事开发配置运行doctor，并清理经逐项确认的空测试目录。2026-10-30仅对保存的部署/CI证据及源码实现作静态复核，没有重跑运行时命令。下方日期段落保留各自时点的环境状态；2026-10-28已由开发CLI交付本机loopback草稿工作台，不能再将旧段落的“尚无前端/HTTP”当作当前状态。本页不包含卡库或引擎资产本体，精确证据见[TESTING](TESTING.md)。

后续首批基线实施新增忽略目录`data/runtime/baseline-2026-10-19/`，包含固定上游数据调查、双资产清点、中文候选、原生批账本/blobs和身份/构建记录。这些是证据，不是纯缓存；旧版或损坏的中间报告也保留，当前使用的报告文件由TESTING明确指定。开发构建与原生运行已分开执行，普通dist及active快照不在本批切换范围。上文旧体积不代表新增后的总占用。

## 当前目录分层

| 路径 | 观察到的内容 | 处理原则 |
|---|---|---|
| `crates/`, `python/`, `schemas/`, `scripts/`, `tests/`, `knowledge/`, `configs/` | 源码、数据工具、合同、构建脚本、夹具和知识包 | Git 管理；禁止混入本地运行产物或机器绝对路径 |
| `data/runtime/` | 约 1.71 GiB、约 59k 文件；含 CDB、ocgcore/Lua、清单、历史原生报告、快照及实验输出 | 本机忽略数据。不是纯缓存；删改前查验收报告/内容寻址账本引用并先备份 |
| `data/tmp/` | 约 0.1–0.14 GiB；含约 500 余目录、测试 trace/blob/检查点和 journal 目录，以及 LFLists/core 源码与 Python 构建工具缓存 | 忽略目录但混合了离线构建依赖和诊断证据。只允许按测试生命周期清理可确认临时项；保留固定上游 checkout 和构建缓存供离线构建 |
| `data/snapshots/` | active 指针与内容寻址的卡库/禁限表 JSON 快照 | 本机数据；不可与版本库快照混淆，不应在一般清理中移除 |
| `data/raw/`, `data/normalized/` | 目前只有 `.gitkeep` | 可再生成工作区，不代表受许可卡库可公开提交 |
| `target/` | Rust 编译缓存及独立测试目录；其中还保存原始日志、源码归档、清单和交付证据 | Cargo 编译缓存可重建；历史日志、归档和交付证据不能靠重编译恢复。禁止整体清除，先核对各批引用与保留需求 |
| `dist/ygo-local/` | 本机CLI/worker/fixture/schema和绝对路径配置；2026-10-19重建 | 2026-10-27包内二进制与清单哈希一致，doctor就绪；不证明最新工作区的干净构建，不含独立赛事资产 |
| `.venv/` | 本地 Python 3.14.7 环境，可启动解释器，但检查时未安装 pip 或 pytest | 保留原位；不能假定该环境可执行完整测试。系统Python及独立3.12测试环境分别记录 |

文件数/体积来自前次本地目录扫描；少数由系统保护的pip临时子目录可能未被递归读取。不要将此处统计当作本轮重新测量或精确配额。

## 2026-10-30 pytest默认收集边界

`pyproject.toml` 将默认 `testpaths` 固定为 `tests/`，缓存仍写到忽略的 `target/pytest-cache`。修复前从仓库根目录直接运行 `py -m pytest` 会继续递归扫描忽略的 `data/runtime/`，在受ACL保护的测试临时目录触发512个collection权限错误并停止；不是512个断言失败。修复后默认collect-only只发现`tests/`的767项，未进入runtime。完整用例仍须单独查看[TESTING](TESTING.md)的本轮结果；被保护的历史材料保持原位。

## 2026-10-31 普通包现场诊断

当前源码已推进到`main / a8d6356`，普通`dist/ygo-local`仍是2026-10-19本地包。普通包及`data/runtime/tournament-2026/engine.toml`赛事配置的现场doctor均退出0并返回`ready=true`、`abi_ok=true`、`assets_ok=true`、`issues=[]`、`smoke_ok=null`。普通包CLI/worker哈希匹配清单，六项路径存在。两次doctor调用worker的ABI探针；未运行决斗smoke、未重新部署或切换资产。输出和CI复验见[TESTING](TESTING.md#2026-10-31-合并ci与普通包现场复核)。

## 2026-10-31 依赖与工具清点

Rust workspace依赖树存在两个`hashbrown`版本：0.14.5由`hashlink/rusqlite`路径使用，0.17.1由`indexmap/toml_edit`路径使用；是不同的传递依赖链，没有从当前图证明可安全统一或删除。`cargo-machete`未安装，因此本轮没有声称完成机器化未用依赖扫描。仓库没有Node/npm、Go或独立requirements/poetry/pipenv清单；Rust以workspace Cargo清单为准，Python依赖集中在`pyproject.toml`。未发现可由包清单安全确认的弃用模块，故保留兼容路径和历史证据。

## 构建与发布状态

- 构建/部署脚本：`scripts/build-engine.ps1`、`scripts/deploy-local.ps1`。支持 `-Offline`；部署使用 `-FrozenRuntime` 时不从 Project Ignis 覆盖已冻结资产。
- 引擎资产由 `data/runtime/engine/manifest.json` 绑定 core、Lua、API、ABI 与哈希；牌库和脚本来自本机准备流程。禁止把 DLL、Lua 脚本、完整 CDB、图片或绝对路径提交到 Git。
- `dist/ygo-local/configs/engine.toml` 和忽略的 `configs/engine.toml` 将 worker 与资产路径写成当前仓库/机器的绝对路径。移动仓库或运行时资产后必须重新部署；该目录不是可任意转发的通用分发包。
- 本地构建包含 Project Ignis/ocgcore 产物，但仓库尚无完整、逐资产的第三方许可/再分发清单。任何公开分发前，先核查上游许可证和每项资产的再分发权限；本地隔离部署不构成可再分发授权。

### 两套运行资产与后续产品前提

- 普通发布wrapper引用普通runtime、普通快照和Phantom知识。赛事开发配置另引用 `data/runtime/tournament-2026/frozen` 与debug worker；2026-10-27两套配置的doctor均就绪，`smoke_ok=null`；随后普通包单独smoke和replay通过，赛事开发配置的固定案例和重放也在独立账本通过；这仍不是统一双资产发布验收。
- 2026-10-19赛事知识来源校验通过但完整语义覆盖仍false；静态包的灰响应声明与运行时独立认证不是同一状态，详见[首回合验真](FIRST_TURN_VERIFICATION.md)。2026-10-27没有重复该业务校验。
- （截至2026-10-27自检）Rust/Python和现有离线资产可用于继续迭代；Node/npm入口存在，但当时尚无前端工程/HTTP服务。已抽查英文卡名，尚未落实中文名称/正文的完整可信来源；不把WindBot中文对白当中文卡库。
- 硬件CIM读取在规划调研时权限受限，未取得全卡求解的资源容量证据。完整证明、前端依赖、中文数据与干净机器部署均须各自验证；不能由doctor推出足够算力或可分发性。
- 更新与引擎更换的未来要求见[产品愿景](PRODUCT_VISION.md)及[路线图](ROADMAP.md)；本次未执行资产更新或安装。

## 2026-10-28开发CLI工作台补记

截至2026-10-28，开发源码中的`ygo-cli workbench serve`提供绑定`127.0.0.1`的草稿网页及本机HTTP端点，支持草稿列表/读写、YDK/JSON导入导出，以及可选本地catalog名称和39卡字段状态读取。页面通过集成测试和隔离浏览器完成草稿编辑、保存、刷新后重开验收；浏览器下载事件未在工具时限内返回，本地文件选择受扩展访问限制，因此浏览器手工操作不等同完整文件选择/下载用户验收，导入导出由HTTP集成测试覆盖。

该入口只管理草稿，不提供牌组分析、自动构筑、研究任务或证明服务。标准库HTTP/1.1实现采用固定loopback与请求限制；新增外部HTTP库的下载因TLS客户端凭据错误`SEC_E_NO_CREDENTIALS`未成功，故需要持续审阅协议边界和维护成本。工作台尚未进入`dist/ygo-local`普通旧包；本节不证明可分发、许可证充分、干净环境安装或当前源码部署通过。历史段落中“尚无前端/HTTP”只描述2026-10-27状态。

## 2026-10-30部署与CI证据界限

保存的2026-10-29记录显示，旧普通包CLI和worker哈希匹配其`build-hashes.json`，主要配置资产路径存在，包内doctor返回ready；包仍是2026-10-19版本且没有workbench命令。PR #8的干净Windows CI在修复提交上通过Python 740/21/0。上述结果各自只覆盖对应包或提交，不能证明当前源码已进入普通包，也不能替代P4-R5独立干净双资产验收。

当前源码`engine doctor`经`crates/ygo-engine-adapter/src/process.rs`中的ABI探针路径调用worker。旧普通包doctor曾执行且有结果记录，但没有足够的同版本运行日志证明其具体内部进程副作用；仅将该次行为标为未知。此处不把“未运行决斗smoke”写成“未启动worker”。

最新Ground Collapse离线准备将证据和测试材料保存在独立runtime及target目录；其交付体积清单约7.33GB且记录一项ACL访问失败，不能当作全工作区或所有证据的完整体积。本次未重新统计，也未调整ACL或删除这些材料。

## 2026-10-30 W1设计后工作区复核（历史时点）

当次核对基线为分支`codex/w1-workbench-analysis-design-20261030`、HEAD `8315232`，工作区起始干净。该分支包含W1受限分析接入设计，任务接口尚未实现。普通`dist/ygo-local`的CLI/worker SHA-256与其`build-hashes.json`相符；engine.toml列出的worker、core、catalog、scripts、script manifest及engine manifest六个路径均存在。该核对没有运行包内程序、没有重新检查所有资产内容，也不能证明后续源码已部署或发布包可移植。

历史普通包doctor内部进程行为仍未知。当前源码doctor经worker执行ABI探针，但不将该源码行为推断为旧包行为。W1接口设计不能视为普通包具备分析功能；部署与工作台边界见[DEPLOYMENT](DEPLOYMENT.md)、[WORKBENCH](WORKBENCH.md)及[W1后路线](superpowers/plans/2026-10-30-post-w1-project-route.md)。

## 2026-10-27 接续容量清点

只读扫描可读取普通文件的逻辑大小：`target/`约106.64 GiB、1,498,674个文件，`data/`约112.86 GiB、307,115个文件，其中`data/runtime/`约112.59 GiB。共有85处访问错误，扫描不跟随reparse点、不去重硬链接，且期间有并发写入；这些是有盲区的时点逻辑大小，不是精确磁盘占用。机器D盘当时可用约95.1 GiB。 恢复后以提升权限对这85个路径逐项执行lstat及直接子项枚举：均可读取，58个当前为空，27个非空项属于隔离Python依赖目录；没有递归复测容量，初次统计仍是有盲区的时点数值。详情见`target/workspace-audit-2026-10-27-codex/capacity-errors-recheck.json`。复核后只非递归移除本轮中断pip留下的5个已确认空目录，逐项核对父目录、名称和非链接状态，记录为`pip-empty-cleanup.json`；其他53个空目录及27个非空目录保持原位。原始范围、分组和错误列表见`target/workspace-audit-2026-10-27-codex/capacity-inventory.json`。

较大分组包括`target/curry-option-validation-tests`约17.09 GiB、`target/debug`约12.90 GiB，以及多个6–12 GiB历史runtime批次。`target/debug/ygo-engine-worker.exe`、`target/release`和若干研究目录仍有配置、部署脚本或证据消费者；大小本身不足以证明可删除。`target/pytest-cache`为可重建缓存，本轮检查时只有875字节。分类、保留引用和迁移方案尚未全面完成，禁止按顶层目录批量清除。 本次仅移除新建的`target/workspace-audit-2026-10-27-codex/cargo`编译缓存：清理前核查精确解析路径、无reparse和无运行中的编译进程；估算可释放约5.76 GiB分配量，日志及其他审计材料在父目录保留。详见`target/workspace-audit-2026-10-27-codex/cargo-cache-cleanup.json`。容量扫描发生在清理之前。

## 2026-10-27 环境自检与缓存处理

- 检查了根目录222个`pytest-cache-files-*`、四个`.v5-package-test-*`及`tests/`下三个`tmp*`目录；各项均可在提升权限后读取、没有子项、不是链接。逐项复核解析路径及空目录状态后非递归删除，共229个；未调整ACL。检查与删除清单位于`target/workspace-audit-2026-10-27-codex/`。
- `pyproject.toml` 将pytest缓存放在被忽略的 `target/pytest-cache`。Windows权限受限时先运行 `New-Item -ItemType Directory -Force -Path target/pytest-cache | Out-Null`；未预建时pytest仍可能留下受限临时目录，但位置在被忽略的`target/`下。
- 最近Ground源码归档包含 `tests/.tenki-*` 下53个文件和 `crates/ygo-engine-adapter/data/tmp/` 下8个文件；这些是合成测试产物，但也是已冻结归档成员，现保留原路径。`.gitignore` 是Ground固定工具包成员，未为清理而改写。
- v1–v5规划、旧提示匹配及历史研究入口均有现用路由、公开接口或证据消费者，未按名称删除。只移除 `ygo-cli` 未直接使用的`toml`及 `ygo-search` 未直接使用的`sha2`依赖声明，其他crate继续依赖对应库。

## 2026-10-27 提交前复核补充

- `.gitignore` 将crate内`data/tmp/`、`data/runtime/`与可中断测试目录`tests/.tenki-*/`纳入本机产物忽略范围；crate runtime仍含历史验证材料，不能据忽略规则推断可删除。
- 再核对冻结603项归档时，确认五个`tests/.tenki-*`临时目录中的53个文件本身是归档成员；这些文件从归档按清单逐项哈希恢复。此处历史内容保持在原路径，忽略规则只避免误纳入后续提交。
- `crates/ygo-engine-adapter/data/tmp/`中的两个随机确认ledger与`data/runtime/tenki-confirmation-tests-target/`共196个文件，仅看到110个header与86个checkpoint记录、未见收费记录；源码未找到该测试目录的精确字符串引用。考虑历史保留用途尚未完全确证，本轮不删除。文件级清单和保留结论见`target/workspace-audit-2026-10-27-codex/nested-synthetic-cleanup.json`；v3验证基线`data/runtime/p1-tenki-placement-validation-native-2026-10-23/`原位保留。

## Windows深路径诊断

Python 3.12隔离全套的首次副本位于本仓库深层`target/`，部分合成测试又在副本内创建嵌套Git仓库，导致Git的`-C`工作目录超过本机路径限制；`git check-ignore`退出128，调用层将其报告为`output must be ignored`。两个相同源码的端到端测试在`C:/ProjectIgnis/codex-ci-audit-20261027`短路径独立副本通过。深路径全套在28%时主动停止，不能算完整测试结果；日志及对照见`target/workspace-audit-2026-10-27-codex/ci-e2e-repro.log`和`ci-short-e2e.log`。

后续`checked_output`已改为只接受两个Git检查的退出码0/1，其他退出码失败关闭，不再把Git错误解释为正常忽略或未跟踪状态；聚焦回归见[TESTING](TESTING.md)。遇到类似错误先检查实际Git退出码、stderr与路径长度；不要只根据上层错误判定忽略规则错误。短路径只是验证环境调整，不改变保存报告或原生scope的身份要求，也不保证其他机器的Git长路径配置。

## 清理决策

除上述明确记录的隔离Cargo缓存和本轮5个空pip临时目录外，本轮没有删除 `data/runtime/`、`data/tmp/`、`dist/`、`target/` 或 `.venv/` 中的其他内容。较大的旧 ash/goal/v5 报告可能是当前文档数字的原始证据，测试账本 blob 可能被重放引用，离线构建 checkout 也有价值。下一次清理应先：

1. 列出受版本控制文档引用的本机报告、报告 ID 和哈希；把长期保留证据与临时工作文件分开。
2. 为 Rust 测试创建的随机 `journal-test-*`、`*.jsonl.blobs` 目录定义成功/失败两种退出清理及保留期限；保留失败时可复现所需条目。
3. 对历史大报告生成摘要与 SHA-256 清单后再决定压缩/迁移，迁移后更新证据路径。
4. 仅当旧部署报告已归档且新部署完成验证后覆盖 `dist/ygo-local`。

禁止用宽泛递归删除命令清理这些混合用途目录。
