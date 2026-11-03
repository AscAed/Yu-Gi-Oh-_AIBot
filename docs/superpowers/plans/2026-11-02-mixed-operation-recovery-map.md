# Mixed accepted/unknown操作恢复顺序映射

本映射先于新增恢复覆盖，固定目标状态、已有证据及唯一进程终止点。当前行为以`crates/ygo-cli/src/workbench_analysis/operation_store.rs::recover_authenticated`为准。

## 源码顺序与目标

`recover_authenticated`先认证操作与任务全部跨链绑定，再按`BTreeMap`操作ID构造待追加操作修订：有匹配任务的accepting变为accepted，无匹配任务的accepting变为unknown。全部操作修订构造完毕后才构造任务分类；发布顺序仍是排序后的操作修订，然后才是任务修订。`recovery_first_operation_classified_before_next`检查点位于每条操作修订追加之后。

新场景直接建立两条存储链：

| 排序 | 操作链原状态 | 绑定任务 | 预期恢复 |
|---|---|---|---|
| `a…a` | allocated→accepting | 无 | unknown revision 3 |
| `c…c` | allocated→accepting→accepting（含冻结输入） | `d…d` queued revision 1，输入与操作完全相同 | accepted revision 4；随后任务转interrupted revision 2 |

唯一K点在第一条操作unknown已提交、第二条操作尚未提交accepted、任务尚未分类之时。父进程必须先认证第一操作链、第二操作链及其queued任务的封套/前驱/记录摘要和交叉绑定，再终止子进程。若握手、状态、排序、关联或事件计数不符，立即停止并保留目录。

## 已有证据对应

| 证据 | 已覆盖 | 本场景仍增加 |
|---|---|---|
| `recovery_first_operation_classified_before_next`现有强杀场景 | 两条直接构造且无任务的accepting操作；第一条unknown后强杀，重开只分类第二条 | 第二条仍需变成accepted；它绑定queued任务，重开后再分类interrupted |
| `recovery_unknown_operation_publish_faults_preserve_later_work_and_resume_once` | 无任务accepting→unknown revision 3的BeforePublish/AfterPublish/Reread | 无匹配任务unknown与匹配queued任务accepted共存时的恢复顺序 |
| `recovery_publish_faults_resume_only_remaining_revisions` | accepted revision 4及interrupted revision 2的P/U/R | 两类操作修复结果混合时的K顺序；不能把单链P/U/R当作混合链顺序证明 |
| `task_commit_before_accepted_is_repaired_without_requeue` | 单条accepting绑定queued任务，重开修复accepted并将queued分类 | 它与先unknown操作共同存在时的排序及进程终止 |

本场景预期恢复不创建、删除或重排工作：强杀前保存材料是1个unknown操作、1个accepting操作及1个queued任务；重开后为2个unknown/accepted终态操作修订和1个interrupted任务修订。不能声称两条操作可由正常HTTP队列同时预占；fixture在存储层直接构造。

## 验收条件和边界

- 子进程使用现有测试专用原子握手和有界等待；父进程验证强杀前`freeze=0`、`claim=0`。
- 强杀前必须精确看到排序`a…a`、`c…c`；第一条unknown revision 3；第二条accepting revision 3；绑定任务queued revision 1且冻结输入一致。
- 实际持锁重开完成第二条accepted及任务interrupted；队列无queued/running，`claim_next`为空；重复重开不追加，操作/任务/报告材料字节稳定。
- 不引入生产API、schema、自动重试或执行器改变。该单一K场景不认证其他排序、其他操作状态组合、P/U/R、逐syscall、断电或介质故障，也不授予真实分析、原生或消费资格。

## 2026-11-02 实际K结果

该映射定义的场景已在`recovery_mixed_operations_first_classified_before_next`挂点完成子进程终止。父进程确认首条`a…a`无任务操作已是unknown revision 3，第二条`c…c`操作为accepting revision 3且绑定`d…d` queued revision 1；冻结输入逐值相等，强杀前事件计数freeze=0、claim=0。恢复后第二条操作为accepted revision 4，任务为interrupted revision 2；队列为空，重复重开后材料字节稳定。

完整工作区运行生成的证据为`target/w1h21-analysis-operation-tests/52d4f1e5727a65f5ebc88ad4b680c587/mixed-operation-recovery-evidence.json`（SHA-256=`C7DD3EF97FA52736AF108C5D844138E849B8CF4B0E36B90741D56B4AD78C2963`）。保存材料从强杀前7个文件增至恢复后9个文件，后者哈希已与`store/`落盘文件逐项复核；两份记录只针对这个直接构造fixture。

本窗口退出后，下一批先从H3.1剩余矩阵筛出W1-C前必需的恢复和调度门禁，再设计固定Rabbit输入、资产身份、预算与停止条件。其他操作/任务排序仍开放；门禁设计不等于真实分析授权。完整命令、套件结果与限制见[TESTING](../../TESTING.md)和[交接](2026-11-02-mixed-operation-recovery-handoff.md)。
