# P1 opcode24 合成菜单交叉核验与交接

## 目标与边界

本批核对 Ground Collapse 候选 `opcode24` 原始合成帧经 Rust 生产提示解码器生成的规范菜单，是否与独立 Python 字节级 oracle 的菜单相符。只验证固定合成掩码下的菜单映射和响应编码；不修改解析器行为，也不运行引擎、runner、worker 或 FFI。

此前的 Ground Collapse 固定来源准备报告仍是只读历史输入，`execution_ready=false`。本批不重跑或覆盖该报告，不创建研究scope、窗口或消费账本。

## 固定夹具

共享夹具[`ground-collapse-opcode24-menu-v1.json`](../../../tests/fixtures/ground-collapse-opcode24-menu-v1.json)由`ygo_eval.ground_collapse_protocol`独立oracle按固定帧`[24,0,2,224,255,224,255]`和掩码`0xffe0ffe0`生成，大小20,144字节，SHA-256为`904b4095fd81666c8336c2ea35ce77d0bbcdaa252ce74dbed43960d1eefe0d33`。该合成掩码有10个可用区域，45个规范无序区域对，并可组成90种语法上不同的有序编码。90只是排列计数，不表示90种都被核心接受或构成不同游戏动作。

Rust集成测试逐项比较生产解析器的`Choice`、卡号列表及响应字节，并验证固定的正序响应可编码、反序Choice不在当前规范菜单中。Python回归验证共享夹具与独立oracle重算一致。测试保留`native_reachability_verified=false`、`native_response_acceptance_verified=false`和`order_equivalence_verified=false`。

## 2026-11-03 验证

- `cargo test -p ygo-engine-adapter --test prompt_actions --offline --locked --target-dir target/p1-opcode24-20261103/rust -- --test-threads=1`：5 passed，0 failed。
- `PYTHONPATH=python py -m pytest -c target/p1-opcode24-20261103/pytest.ini -p no:cacheprovider -q -ra --tb=short tests/test_ground_collapse_protocol.py`：9 passed。
- `PYTHONPATH=python py -m pytest -c target/p1-20261103/pytest.ini -p no:cacheprovider -q -ra --tb=short tests/test_information_projection.py tests/test_information_route_projection.py`：29 passed、11 subtests passed。
- `cargo fmt --all -- --check`及`cargo clippy -p ygo-engine-adapter --all-targets --offline --locked --target-dir target/p1-opcode24-20261103/rust -- -D warnings`通过。

pytest缓存插件在target和系统临时目录创建缓存时都遇到Windows`WinError 5`。最终聚焦运行使用target内的最小pytest配置并禁用缓存插件；没有跳过测试。此验证未运行workspace全套测试。

## 结果与续接

Rust生产解码器与独立Python oracle在此固定合成输入上逐项一致；未发现该限定菜单映射的差异。当前解析器为每个无序区域对只生成一个规范顺序，不能据此判断反序响应的原生合法性。实际opcode24提示、可达性、prompt ID、核心接受响应、反序等价、后续消息序列及全动作覆盖仍未知；P1完整问题和最优性资格保持开放。

后续如要回答真实动作合法性，须先为新的独立研究批次定义输入/资产身份、预算、停止条件和证据合同，再取得单独授权。首次原生提示不匹配、掩码/计数变化、菜单或响应字节差异、额外未知消息、资产漂移及消费不确定都应停止并保留材料；不得直接使用本夹具或旧准备报告启动执行。
