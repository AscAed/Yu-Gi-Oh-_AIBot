# Ground Collapse opcode24候选执行清单离线评审

## 结论与边界

本记录完成Ground Collapse固定案例的当前源码、隔离构建、阶段请求、冻结输入和本机资产身份离线绑定，供后续独立审阅。机器记录位于忽略路径`target/p1-ground-collapse-candidate-manifest/reviewed-candidate-manifest.json`，类型为`ground_collapse_candidate_manifest_review_v1`。它是待审的候选身份清单，不是可供runner消费的scope manifest。

候选保持 **hold**：当前准备报告`execution_ready=false`，本清单`scope_created=false`、`scope_authorized=false`，`native_request_sha256=null`、`actual_prompt_ids=null`，没有窗口起点或真实收费请求。实验设计中的最多5个预算请求、1,800秒窗口和单次请求30,000毫秒仅是未来单独授权后适用的上限，不构成本次授权。任何源码、请求、资产或预算身份漂移、提示不匹配、结果不确定或验收条件失败时，都必须停止并保留证据；不得重试或补发请求。

本次只运行离线verify-only和`cargo build --offline --locked`，并直接读取文件计算哈希。生成runner与worker二进制不等于启动它们。没有创建scope、窗口、账本或运行目录；runner进程、worker进程、引擎及FFI调用均为0。

## 身份与输入

- Git HEAD为`672e5a823fcad60e9413d79cac810b68a2bb003c`。机器清单在所有本文和事实源文档定稿后，重新采集HEAD及全部已跟踪和非忽略未跟踪文件的稳定工作区身份；因此该身份包含现有未提交改动，不把HEAD当作完整工作区身份。
- 当前准备报告`data/runtime/p1-ground-collapse-preparation-current-2026-11-03-driver-review-2/preparation.json`为25,131字节，SHA-256=`a238a2f114c7cb26b6f1e79d6ca34b3e5f01f33bdb57eab0b6d2f650c2bb8c99`。原报告中的710文件工作区值`80827b9571b4fdaa7a2749d4a11a94a2916786486c7bdfae55d85d07853db228`是历史捕获元数据，标记为`historical_capture_metadata_not_reauthenticated`，不作为本次当前源码身份。
- 固定候选为`prompt-24-collapse-v1`，卡号`90502999`，候选案例摘要`ccf3143c589472dc3ea48f2ef1fcf0216f64a55cd5365e2762a26745c036e52b`。派生stage 1请求仅将worker路径绑定到本次隔离构建；请求规范摘要为`c1d95003c27047d78c68e247a3c0590d776508d6251bbb69157b3c31cde617ca`，保存请求文件SHA-256为`47908b74523ef50d402df10a5ea77cecf8f0b6e940654ca21fc01d36b7b398df`。其冻结Rabbit基础请求摘要为`d25d2e79a58728221111d9007f5890b3e99be2bdcf4a8aee1a17554d59da91bb`。stage 1请求不是最终原生scope请求；后者仍为空。
- 最新工具包仍为19个固定成员，ZIP SHA-256=`8fd8bb6ad057f6b83507b28a33adc6281c049974cac5d3e49db723df96515dbc`，成员清单SHA-256=`9e844de98ab205f2243c706aa6b368d2b68a81af65e9c70472d47f8f9689f746`。只读`--verify-only`返回`valid=true`、`preparation_successful=true`，重新核对138个文件输入和5个目录输入。报告历史工作区字段仍只按其原捕获语义解释。

## 隔离构建与资产快照

在隔离目录`target/p1-ground-collapse-candidate-manifest/cargo`运行：

```text
cargo build -p ygo-engine-adapter --example ground-collapse-probe --bin ygo-engine-worker --offline --locked --target-dir target/p1-ground-collapse-candidate-manifest/cargo
```

构建命令成功，产物SHA-256如下：

| 产物 | SHA-256 |
|---|---|
| `examples/ground-collapse-probe.exe` | `cfbdea40902a0084ea8dfba9be5218591d899ef1a11a93a1ae76858dbbd89469` |
| `ygo-engine-worker.exe` | `526f793ab41505132d7a7e6b0d460373914b235eeb6f01b43a41c881b6362819` |

最终机器清单引用文档定稿后的build record及其源码前后身份。记录器声明`provenance=observed_command_only`、`reproducible_build_proven=false`；该证据表示观察到的本地命令和产物哈希，不声称可复现构建证明。

资产快照位于`target/p1-ground-collapse-candidate-manifest/asset-snapshot.json`，SHA-256=`7fbbb001e0b85670f57cfcc4a6708115a7b80cc167c0a1896419f4834fe6b6fe`。当前快照确认DLL、CDB、engine manifest、scripts manifest、禁限表、目标脚本、六个固定core源码文件及worker均匹配保存值。生产目录快照算法覆盖脚本树12,728个条目（12,727个文件），SHA-256=`4f32b4aadc675437a03aa6adff7666cfce9d60e9846fd354d8b0354786d26d29`。这些是离线字节身份检查，不证明资产已加载、适用于将来的scope或执行时仍保持相同。

## 复核结果及未覆盖内容

命令行`--verify-only`成功退出，结果为`valid=true`、`preparation_successful=true`，且native、runner、worker、FFI调用均为0。verify-only耗时约107秒。最初一次参数路径顺序写反，固定profile拒绝了该调用且没有写入输出；修正参数后复核成功，原报告字节与摘要保持不变。

待审机器清单以原子临时文件写入并同步后发布，随后对其字段、源码身份、请求规范摘要、build record、产物哈希、快照及准备报告标志进行独立只读复核。它显式保留未授权状态和空的原生请求/prompt字段。没有创建或验证scope消费账本，也没有运行doctor、真实引擎、runner、worker或FFI。

本记录只把当前固定案例和离线执行候选绑定到一起，不证明opcode24可达、响应被接受、消费量、全动作、概率、独立重放、部署资格或全局最优性。清单已通过独立只读审阅；下一步为单次窗口执行准入决策，真实scope仍需另行明确授权。其他P1研究障碍、W1-C/R1b-3、P4发布门禁、W2和全卡/全局最优研究均保持各自状态。
