# 证据身份、版本与发布合同

本文说明已实现的证据绑定及其适用范围，不新增schema字段或认证资格。当前任务/累计会计见[TASKS](../TASKS.md)，最新实际验证见[TESTING](TESTING.md)，运行副作用见[RESEARCH_OPERATIONS](RESEARCH_OPERATIONS.md)。依据是当前代码、schema及保存产物；旧计划和交接用于定位历史，不能替代当前实现。

标记约定：**已验证·指定版本**只覆盖所链接实现和记录；**仅历史scope**只描述相应冻结实验；**拟议改善**不是现有保证。本文不把最新累计数字或文件哈希复制成第二份事实源。

## 对象身份与文件字节分开

**已验证·identity v1：**[Python canonical函数](../python/ygo_data/identity.py)采用UTF-8、键排序、紧凑分隔符与`ensure_ascii=False`。workspace source identity对`{head, files}`对象计算SHA256，`files`含tracked及非忽略untracked文件的内容哈希，并用`null`保留删除项；对象自身的`identity`字段不参与其原始待散列对象。源码内容身份不是只有Git commit，也不是dirty布尔值或时间戳。

**已验证·按合同选对象：**engine identity、workspace identity、build record和tool identity各有自己的待散列字段集合。build record的内容身份含构建前后源码、命令哈希、工具链、退出状态及产物；恢复V3工具身份绑定文件映射和workspace identity。不得把任意报告删去某几个字段后当作通用canonical合同。尤其[账本](../crates/ygo-engine-adapter/src/journal.rs)链使用序号、前hash及entry的规定序列化，[Ground账本核验](../python/ygo_eval/ground_collapse_preparation.py)重建对应顺序；不能擅自换成普通JSON键排序。

| 被绑定对象 | 哈希回答的问题 | 不足以回答的问题 |
|---|---|---|
| canonical对象身份 | 规定字段在该合同中是否相同 | 外部JSON原始排版/换行是否相同，来源是否可信 |
| 原始JSON/报告文件SHA256及长度 | 保存的精确字节是否相同 | 与另一个排版对象是否同义，业务检查是否通过 |
| ZIP容器SHA256及长度 | 是否为同一个归档文件字节序列 | 成员是否符合期望源码、是否安全或完整 |
| 文件清单原始字节SHA256 | 是否为同一清单文件 | 成员实际存在、ZIP内容与清单相符 |
| ZIP成员名、成员原始字节SHA256及集合 | 内容是否逐项绑定，是否缺失/额外/重名 | 构建实际执行过，资产可加载或规则正确 |
| build record对象身份与文件SHA256 | 记录语义及保存字节各自绑定 | 可复现构建、每个二进制必为该命令新生成 |

**已验证·归档核验：**[Ground准备器](../python/ygo_eval/ground_collapse_preparation.py)核验固定ZIP/清单原始哈希，再对精确成员集合、每项成员哈希及source identity交叉检查；[恢复器](../python/ygo_eval/curry_ledger_handoff_recovery.py)也独立核验工具包。容器压缩方式、元数据、成员顺序或JSON排版变化可改变容器/文件哈希，即使成员内容或canonical对象相同。记录中应明确字段表示哪层身份，不能混用ZIP哈希、清单哈希与源码identity。

链接、junction、重解析点、路径逃逸及非普通文件的保护由具体读取器实现；精确集合门禁有版本范围。不能为了让旧根“变干净”而移动失败侧车、改名旧目录或删除额外文件。原始来源、清单和归档应保留原字节；静态核验历史归档不需要执行其中代码。

## DLL、worker与逻辑角色

**已验证·engine identity v1：**[schema](../schemas/engine-identity.schema.json)及[采集实现](../crates/ygo-engine-adapter/src/identity.rs)分别绑定`worker`、`dll`、`cdb`、`script_manifest`、`engine_manifest`，并保存实际脚本树、missing/extra/mismatch和timeout。DLL承担ocgcore效果执行；worker是加载库、读取资产并通过进程协议服务请求的适配程序；runner是其外层研究调度/审计程序。三者的文件哈希和逻辑角色不能互换。

`consistent`只覆盖文件齐全、双采样稳定及脚本清单与实际字节一致。engine manifest按原始字节散列，不在身份采集时证明其ABI/构建声明；DLL加载性、ABI和运行效果需要其他证据。读取DLL哈希不执行FFI；worker路径存在也不证明它已启动。[BASELINE_AUDIT](BASELINE_AUDIT.md)保留这些边界。

**已验证·构建记录v1：**[schema](../schemas/build-record.schema.json)将来源限定为`observed_command_only`，`reproducible_build_proven=false`。一次成功命令及产物哈希关联不独立证明产物都是该命令新生成。相同二进制哈希也不能补出缺失的源码关联。部署后改名的CLI与原名称按角色和字节绑定，不能因文件名像新CLI就调用未确认命令。

**仅历史scope：**Curry恢复V2期望`v3_source_confirmation_summary`，真实保存来源却是`v3_source_workspace_identity`，因而在角色门禁失败；V3修正为唯一真实角色，没有建立宽泛别名。[V2失败交接](superpowers/plans/2026-10-26-curry-ledger-handoff-recovery-v2-handoff.md)和[V3恢复交接](superpowers/plans/2026-10-26-curry-ledger-handoff-recovery-v3-handoff.md)均需保留。输入角色数、物理路径数和证据别名数不是同一计数：多个角色可绑定同一物理字节，不能据路径去重删掉合同角色。

## 合同版本、stdout与进程记录

**已验证·当前版本表：**[handoff audit实现](../python/ygo_eval/curry_ledger_handoff_audit.py)保留V1–V5独立schema与检查序列；V1–V3使用`legacy-v1` stdout合同，V4/V5选择`verification-accounting-v1`。旧三字段对象与真实附加会计字段的stdout不能靠忽略额外字段混为相同。V3真实审计的父收据stdout门禁失败与V4的版本适配分别记录于[V3交接](superpowers/plans/2026-10-26-curry-ledger-handoff-v3-handoff.md)、[V4交接](superpowers/plans/2026-10-26-curry-ledger-handoff-v4-handoff.md)。

**已验证·恢复版本：**[恢复器](../python/ygo_eval/curry_ledger_handoff_recovery.py)保留恢复V1/V2/V3各自schema、工具成员集和输入角色集合；恢复报告版本、原审计报告版本、worker协议版本和stdout合同版本分别选取，不能将它们都简称为“V3”。V3恢复对真实V5进程材料使用保存的专用stdout合同；旧schema和失败文件不被新成功结果覆盖。

**已验证·stdout分层：**runner机器输出是对应模式的一份JSON；阶段日志/诊断属于stderr或单独侧车。保存stdout/stderr的原始字节、长度、SHA256、退出码、超时和进程元数据；解析后的JSON对象另按合同核验。不要从打印的摘要重新编码“还原”原始stdout，不要把外层Python输出当作内层runner输出，也不要只留终端抄录。恢复V3中报告文件字节哈希和stdout哈希不同，不能因解析对象相关就互相替代，见[V3真实恢复交接](superpowers/plans/2026-10-26-curry-ledger-handoff-recovery-v3-handoff.md)。

**仅历史scope·V5：**保存输入runner退出0且输出其自身检查通过，但外层退出2、正式`audit-report.json`缺失。因此[V5进程侧车](../data/runtime/p1-curry-ledger-handoff-v5-offline-2026-10-26/process-diagnostics/)与[外层日志](../target/curry-ledger-handoff-v5-tests/audit-command.log)是独立失败观察，不是已发布的V5合同报告。原内部异常未被认证，后续恢复的诊断不能改写原进程结论。

## 原生时点身份与文档后身份

**已验证·具备双时点材料的指定批次：**Curry再验真按其合同绑定执行当时的源码归档、文件清单、build record、runner/worker/CLI字节、资产身份、请求及账本。文档收尾会改变workspace identity，最终交付另外绑定完整当前源码及材料索引。不能用文档后identity替换原生时点build record的source identity，也不能反向声称旧二进制对应包含新文档/源码的完整最终工作区。这不是所有历史原生批次都已具备的保证：早期九次请求的旧runner来源不可得，缺失或未认证来源保持未知；当前归档、哈希或后续成功不能为它补签，见[独立历史核验交接](superpowers/plans/2026-10-21-history-followup-handoff.md)及[历史完整性工具边界](RESEARCH_AUDIT.md)。

**仅历史scope·Curry再验真：**[交接](superpowers/plans/2026-10-27-curry-option-revalidation-handoff.md)及[最终delivery](../data/runtime/p1-curry-option-revalidation-native-2026-10-26/final-build/delivery-final.json)分别保留原生时点与最终源码/构建材料。[Ground最终delivery](../target/ground-collapse-preparation-tests/final-release/delivery.json)进一步固定这两份来源。文档修改不为旧原生结果新增规则资格；最终身份变化也不表示原生证据失效，应按各自绑定及允许源码差异检查。

**已验证·恢复V3的细节：**成功报告发布重建要求工具身份绑定本次workspace，发布源签名包含`tool`；保存报告的verify-only允许文档更新后workspace变化，但仍核验保存工具包及来源，并要求本次读取稳定。这个兼容不是“忽略任意源码变化”，更不是允许篡改旧报告。[恢复器](../python/ygo_eval/curry_ledger_handoff_recovery.py)与[V3 schema](../schemas/curry-ledger-handoff-recovery-v3.schema.json)是具体边界。

## 报告发布与失败保留

**已验证·恢复V3：**业务检查成功之后仍须完成来源重建、报告/保存schema验证、独占写入、读回相等及写后重建。`status=passed`的内存对象、进程退出0、目标文件存在、发布完成和后续verify有效是不同事实。失败会清除内存成功声称，并按可观察状态记录诊断；不能覆盖已写或已存在的证据来使其看似从未失败。

| 状态/记录 | 适用合同与含义 | 后续边界 |
|---|---|---|
| 业务检查失败，合法失败报告已保存 | 恢复报告schema仍可有效，`status=failed` | 保留失败检查点及`not_run`后继，不据schema通过授予成功 |
| `not_written` | 恢复发布诊断：未写正式文件 | 保留诊断；不猜测存在成功报告 |
| `existing_preserved` | 原目标已存在并被保留 | 不覆盖、删去或换名复用原目标 |
| `write_attempted_unverified` | 写入尝试结果无法充分验证 | 记录诊断与可得hash；不能记为已发布成功 |
| `written_unverified` | 已写报告，但写后复验/来源重建失败或不可认证 | 保存实际报告hash及原字节；不能反写它来修饰失败 |
| 发布passed及只读verify有效 | 对应保存报告完成发布与复验 | 只取得该合同的来源/一致性结论，不自动提升原生或证明资格 |

上述状态来自[发布诊断schema](../schemas/audit-publication-diagnostic-v1.schema.json)与[恢复发布实现](../python/ygo_eval/curry_ledger_handoff_recovery.py)。Ground preparation v1有自己的[发布诊断与准备schema](../schemas/ground-collapse-preparation-v1.schema.json)，不能机械要求其实现恢复器的全部状态字段。报告、工具包、进程侧车、未发布观察、失败目录和ACL访问失败清单各按原范围保留；合成验收通过不能替代唯一真实尝试。

## 资格层级与不可跨越的推论

**已验证·层级解释：**下表是阅读证据的分类，不是新增的机器枚举或单线自动晋级流程；每项资格需要自己的独立证据。

| 证据层 | 可支持的结论 | 仍需另证的内容 |
|---|---|---|
| schema/语义合法 | 对象满足指定结构和局部语义约束 | 来源真实性、引擎执行、合法规则 |
| 字节、角色、归档与链认证 | 指定保存来源未变且关系符合合同 | 原时点未保存的信息、DLL可用性 |
| 合成/静态独立oracle一致 | 指定帧/编码/负例可区分且比较一致 | 实际提示可达、响应被原生接受 |
| 冻结原生分支及独立重放 | 已执行前缀和指定分支可复验 | 未触达分支、完整动作集合、真实概率 |
| `execution_ready` | 对应准备合同允许的准入状态 | 不自动授予worker执行授权；Ground当前为false |
| 完整性、概率与最优性证明 | 需要完整动作、信息策略、机会状态、循环与独立值界等证据 | 现有局部案例不能提供这些整体资格 |

**仅历史scope：**Tenki opcode13与Curry opcode14的部分分支及独立重放，只适用于各自冻结案例；Ground opcode24的45个canonical区域对/90种有序编码来自静态与合成材料。实际mask、prompt ID、可达性、响应接受、反序等价与后继仍未知；FIELD_DISABLED56解析支持也不证明该消息在真实Ground线路出现。见[Ground交接](superpowers/plans/2026-10-27-ground-collapse-preparation-handoff.md)。

**已验证·现有资格边界：**`proof_ready`、`complete_action_coverage`、`global_optimality`、`native_probability_verified`继续为false。内容身份、成功恢复、预算预留、schema通过或局部原生重放均不能单独改变这些值。发行依据unknown也不能靠卡库行数、脚本存在或中文候选资料补齐。未知消费保持`null`，未知效果/来源明确保留未知，不填0或自签为engine-verified。

**拟议改善：**为新证据入口统一文档化“对象身份算法、原始文件hash、容器/成员核验、模式副作用、发布状态、可授予资格”六项清单，并用合成负例覆盖混淆；既有合同保持按版本读取，不以通用宽容解析替代精确历史约束。
