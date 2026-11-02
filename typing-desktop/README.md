# typing-desktop

“词间”桌面端（Tauri 2 + Rust），开发中。设计见 [docs/typing-desktop/DESIGN.md](../docs/typing-desktop/DESIGN.md)。

## FSRS 对照基准

在仓库根目录用 py-fsrs 生成 Rust 实现的比对数据（输出可复现）：

```powershell
.\.venv\Scripts\python.exe typing-desktop\scripts\gen_fsrs_fixtures.py
```

输出 `fixtures/fsrs-golden.json`。修改 `typing-practice/backend/srs.py` 的评分或调度规则后需重新生成并提交。

## 测试

需要 Rust 工具链与 MSVC 生成工具（见设计文档“本机环境”）。在 `typing-desktop` 目录运行：

```powershell
cargo test
```

`core/tests/golden.rs` 读取上述基准，逐条比对 Rust 调度、评分与答案归一化结果。
