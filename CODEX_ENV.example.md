# Codex 环境配置示例

复制为仓库根目录的 `CODEX_ENV.md` 后按本机情况修改。`CODEX_ENV.md`
只保存本地/个人配置，不提交到 Git。

## local-gcc

适用于当前机器已安装 64 位 gcc，且可以直接运行 `typing-practice` 后端测试。

```yaml
test_mode: local-gcc
gcc_path: C:\msys64\ucrt64\bin
typing_practice_backend: typing-practice/backend
test_command: python -m unittest discover -s typing-practice/backend -p 'test_*.py'
```

## ssh-server

适用于当前机器不跑测试，由已配置好 SSH 登录的本地服务器执行测试。

```yaml
test_mode: ssh-server
ssh_target: user@server-host
repo_path: /path/to/my-ielts
typing_practice_backend: typing-practice/backend
test_command: python -m unittest discover -s typing-practice/backend -p 'test_*.py'
```

Codex 使用方式：

- `local-gcc`：在本机运行 `test_command`；当前 Python 测试不需要 gcc。
- `ssh-server`：运行 `ssh <ssh_target> "cd <repo_path> && <test_command>"`。
