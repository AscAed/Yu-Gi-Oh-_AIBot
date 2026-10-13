# 引擎适配

EngineAdapter::run 接收 RunDuelRequest，返回 DuelResult 或父进程 WorkerError。ProcessEngineAdapter 调用独立 worker，核心 FFI、只读卡片回调和脚本回调集中在 worker。不会启动 EDOPro GUI。

配置分开指定 worker_path、ocgcore_path、catalog_path、scripts_path、script_manifest_path、engine_manifest_path 和 timeout_ms。旧 GUI 配置因 unknown fields 明确拒绝。doctor 输出资产检查、ABI 检查和未执行 smoke 的 null；真实验收用 engine smoke 和 opt-in golden。

原始消息不直接转成推测卡效；未知信息保留并降低验证等级，未知决策停止分支。细节见 ENGINE_PROTOCOL.md 和 DEPLOYMENT.md。
