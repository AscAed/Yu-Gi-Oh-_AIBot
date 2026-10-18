# 本机环境与资产审计

审计日期：2026-10-19。目录大小来自前次完整自检观察，会随实验和构建变化；本轮文档交付未重新扫描体积，仅重查配置、二进制哈希及doctor。本页不包含任何卡库或引擎资产本体，精确验证见[TESTING](TESTING.md)。

## 当前目录分层

| 路径 | 观察到的内容 | 处理原则 |
|---|---|---|
| `crates/`, `python/`, `schemas/`, `scripts/`, `tests/`, `knowledge/`, `configs/` | 源码、数据工具、合同、构建脚本、夹具和知识包 | Git 管理；禁止混入本地运行产物或机器绝对路径 |
| `data/runtime/` | 约 1.71 GiB、约 59k 文件；含 CDB、ocgcore/Lua、清单、历史原生报告、快照及实验输出 | 本机忽略数据。不是纯缓存；删改前查验收报告/内容寻址账本引用并先备份 |
| `data/tmp/` | 约 0.1–0.14 GiB；含约 500 余目录、测试 trace/blob/检查点和 journal 目录，以及 LFLists/core 源码与 Python 构建工具缓存 | 忽略目录但混合了离线构建依赖和诊断证据。只允许按测试生命周期清理可确认临时项；保留固定上游 checkout 和构建缓存供离线构建 |
| `data/snapshots/` | active 指针与内容寻址的卡库/禁限表 JSON 快照 | 本机数据；不可与版本库快照混淆，不应在一般清理中移除 |
| `data/raw/`, `data/normalized/` | 目前只有 `.gitkeep` | 可再生成工作区，不代表受许可卡库可公开提交 |
| `target/` | Rust 编译缓存约 12.2 GiB | 可再生成；本轮保留以复用编译结果。清理将增加完整重编译时间 |
| `dist/ygo-local/` | 本机CLI/worker/fixture/schema和绝对路径配置；前次自检已于2026-10-19重建 | 本轮哈希与现存release及包内清单一致，doctor就绪；不证明最新工作区的干净构建，不含独立赛事资产 |
| `.venv/` | 本地 Python 环境 | 可再生成，但保持已有环境以便完整 Python 验证 |

文件数/体积来自前次本地目录扫描；少数由系统保护的pip临时子目录可能未被递归读取。不要将此处统计当作本轮重新测量或精确配额。

## 构建与发布状态

- 构建/部署脚本：`scripts/build-engine.ps1`、`scripts/deploy-local.ps1`。支持 `-Offline`；部署使用 `-FrozenRuntime` 时不从 Project Ignis 覆盖已冻结资产。
- 引擎资产由 `data/runtime/engine/manifest.json` 绑定 core、Lua、API、ABI 与哈希；牌库和脚本来自本机准备流程。禁止把 DLL、Lua 脚本、完整 CDB、图片或绝对路径提交到 Git。
- `dist/ygo-local/configs/engine.toml` 和忽略的 `configs/engine.toml` 将 worker 与资产路径写成当前仓库/机器的绝对路径。移动仓库或运行时资产后必须重新部署；该目录不是可任意转发的通用分发包。
- 本地构建包含 Project Ignis/ocgcore 产物，但仓库尚无完整、逐资产的第三方许可/再分发清单。任何公开分发前，先核查上游许可证和每项资产的再分发权限；本地隔离部署不构成可再分发授权。

### 两套运行资产与后续产品前提

- 普通发布wrapper引用普通runtime、普通快照和Phantom知识。赛事开发配置另引用 `data/runtime/tournament-2026/frozen` 与debug worker；本轮各自doctor通过不等于已有统一双资产发布包或正式v6。
- 本轮赛事知识来源校验通过但完整语义覆盖仍false；静态包的灰响应声明与运行时独立认证不是同一状态，详见[首回合验真](FIRST_TURN_VERIFICATION.md)。
- Rust/Python和现有离线资产可用于继续迭代；Node/npm入口存在，但尚无前端工程/HTTP服务。已抽查英文卡名，尚未落实中文名称/正文的完整可信来源；不把WindBot中文对白当中文卡库。
- 硬件CIM读取在规划调研时权限受限，未取得全卡求解的资源容量证据。完整证明、前端依赖、中文数据与干净机器部署均须各自验证；不能由doctor推出足够算力或可分发性。
- 更新与引擎更换的未来要求见[产品愿景](PRODUCT_VISION.md)及[路线图](ROADMAP.md)；本轮未执行资产更新、安装或清理。

## 清理决策

本轮没有删除 `data/runtime/`、`data/tmp/`、`dist/`、`target/` 或 `.venv/` 中的内容。较大的旧 ash/goal/v5 报告可能是当前文档数字的原始证据，测试账本 blob 可能被重放引用，离线构建 checkout 也有价值。下一次清理应先：

1. 列出受版本控制文档引用的本机报告、报告 ID 和哈希；把长期保留证据与临时工作文件分开。
2. 为 Rust 测试创建的随机 `journal-test-*`、`*.jsonl.blobs` 目录定义成功/失败两种退出清理及保留期限；保留失败时可复现所需条目。
3. 对历史大报告生成摘要与 SHA-256 清单后再决定压缩/迁移，迁移后更新证据路径。
4. 仅当旧部署报告已归档且新部署完成验证后覆盖 `dist/ygo-local`。

禁止用宽泛递归删除命令清理这些混合用途目录。
