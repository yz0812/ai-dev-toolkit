---
name: ac-commit
description: '分析 Git 改动并生成规范提交信息。'
disable-model-invocation: true
---

# Commit - 主线程提交 + Subagents 辅读分析

分析当前改动，生成 Conventional Commits 风格的提交信息；仅在大 diff 或跨多个关注点时，按需启用只读 subagents 辅助聚类与风险分析。

## 使用方法

```bash
/ac-commit [options]
```

## 参考资料

- `references/conventional-commits.md` — Conventional Commits 规范

## 选项

| 选项 | 说明 |
|------|------|
| `--no-verify` | 跳过 Git 钩子（仅当用户显式指定时） |
| `--all` | 暂存所有改动 |
| `--amend` | 修补上次提交（仅当用户显式指定时） |
| `--signoff` | 附加签名 |
| `--emoji` | 包含 emoji 前缀 |
| `--scope <scope>` | 指定作用域 |
| `--type <type>` | 指定提交类型 |

---

## 角色分工

| 角色 | 职责 |
|------|------|
| Claude（主线程） | 执行 Git 检查、收集 diff、决定是否启用 subagents、生成 commit message、执行提交 |
| subagents | 只读分析大 diff 的聚类结果、拆分建议与风险点，不执行 Git 写操作 |

---

## 执行约束

**工作目录**：
- 使用当前 Git 仓库根目录作为提交分析根目录
- 如果用户通过 `/add-dir` 添加了多个工作区，先确定实际要提交的仓库
- 如果无法确定，用 `AskUserQuestion` 询问用户选择目标仓库

**subagents 使用条件**：
- 适用：diff 很大、跨多个顶级目录、混合了多类关注点（源码/测试/文档/配置）
- 优先：使用只读 subagents 做改动聚类、拆分建议和风险扫描
- 不适用：小改动、单一功能点、主线程直接看 diff 就能判断的场景

**重要**：
- 所有 Git 写操作（`git add`、`git commit`、写 `.git/COMMIT_EDITMSG`、写 `.context/history/*`）只由主线程执行
- subagents 不得执行暂存、提交、改写历史、跳过钩子等 Git 写操作
- 已委托给 subagents 的 diff 分析内容，主线程不要重复分析
- 默认尊重 Git hooks；只有用户显式传入 `--no-verify` 时才可跳过
- 只有用户显式传入 `--amend` 时才允许修补上次提交

---

## 执行工作流

### 🔍 阶段 1：仓库校验

`[模式：检查]`

1. 验证当前目录是 Git 仓库
2. 检测 rebase / merge / cherry-pick 等中间状态与冲突
3. 读取当前分支与 HEAD 状态

### 📋 阶段 2：改动检测

`[模式：分析]`

1. 获取已暂存与未暂存改动
2. 若暂存区为空：
   - 用户显式传入 `--all` → 暂存所有改动
   - 否则提示用户选择是否需要暂存
3. 收集：
   - `git status --short`
   - `git diff --cached`
   - 必要时 `git diff`

### 🧩 阶段 3：拆分建议与按需并行分析

`[模式：建议]`

1. 主线程先快速判断改动规模与关注点
2. 若改动较小，主线程直接按以下维度聚类：
   - 关注点（源代码 vs 文档/测试）
   - 文件模式（不同目录/包）
   - 改动类型（新增 vs 删除）
3. 若检测到以下情况之一，则按需并行启动只读 subagents：
   - 改动超过约 300 行
   - 跨多个顶级目录
   - 同时包含功能、测试、文档、配置等多类改动
4. subagents 典型拆分方式：
   - **改动聚类**：判断哪些文件应归为同一原子提交
   - **风险扫描**：识别 breaking change、配置风险、大量删除、测试缺口
5. 主线程汇总后决定：
   - 是否建议拆分提交
   - 当前提交的最佳 type / scope / subject

### ✍️ 阶段 4：生成提交信息

`[模式：生成]`

**格式**：`[emoji] <type>(<scope>): <subject>`

- 首行 ≤ 72 字符
- 祈使语气
- 消息体：动机、实现要点、影响范围
- 语言：根据最近提交风格与当前仓库习惯判断中文/英文

若已启用 subagents，则结合其聚类与风险分析结果生成更准确的提交信息。

### 📦 阶段 5：Context 自动归档（若 `.context/` 存在）

`[模式：上下文归档]`

**前置判断**：
- 若 `.context/` 目录不存在 → 自动创建 `.context/history/`、`.context/current/branches/` 目录结构，初始化空的 `commits.jsonl` 和 `commits.md`，然后继续执行归档
- 若 `.context/` 存在 → 执行以下步骤

**从 git diff 自动生成 ContextEntry**：

1. 获取当前分支名：`git branch --show-current`
2. 获取暂存区变更：`git diff --cached --stat` + `git diff --cached`
3. 分析 diff 生成 ContextEntry：
   - `summary`：从阶段 4 生成的 commit message 中取首行
   - `decisions`：分析 diff 中的关键变更（新增依赖、架构调整、接口变更、配置修改），推断决策理由
   - `bugs`：若 commit type 为 `fix`，从 diff 中提取 bug 症状、根因、修复方式
   - `changes.files`：从 `git diff --cached --name-only` 提取
   - `tests`：若变更包含测试文件，记录测试相关信息
4. 若 `.context/current/branches/<branch>/session.log` 存在且非空，将其中的手动记录合并到 decisions / bugs 中，然后清空 `session.log`
5. 脱敏：扫描 token / key / password / secret 模式 → 替换为 `[REDACTED]`
6. 追加：将 ContextEntry 作为一行追加到 `.context/history/commits.jsonl`
7. 重生成：更新 `.context/history/commits.md` 人类视图
8. 暂存：`git add .context/history/`
9. Trailer：在 commit message 中添加 `Context-Id: <uuid>` trailer

**失败降级**：若归档过程出错，不阻断提交。写入 minimal ContextEntry（仅 summary + files），继续正常提交。

### ✅ 阶段 6：执行提交

`[模式：执行]`

```bash
git commit [-S] [--no-verify] [-s] -F .git/COMMIT_EDITMSG
```

---

## Type 与 Emoji 映射

| Emoji | Type | 说明 |
|-------|------|------|
| ✨ | `feat` | 新增功能 |
| 🐛 | `fix` | 缺陷修复 |
| 📝 | `docs` | 文档更新 |
| 🎨 | `style` | 代码格式 |
| ♻️ | `refactor` | 重构 |
| ⚡️ | `perf` | 性能优化 |
| ✅ | `test` | 测试相关 |
| 🔧 | `chore` | 构建/工具 |
| 👷 | `ci` | CI/CD |
| ⏪️ | `revert` | 回滚 |

---

## 示例

```bash
/ac-commit
/ac-commit --all
/ac-commit --emoji
/ac-commit --scope ui --type feat --emoji
/ac-commit --amend --signoff
```

## 关键规则

1. **Git 写操作只在主线程** – 提交、暂存、写提交信息都由当前会话主线程完成
2. **subagents 只做大 diff 分析** – 按需使用，不默认开启，不执行 Git 写操作
3. **尊重钩子** – 默认执行，只有用户显式指定 `--no-verify` 才可跳过
4. **原子提交** – 一次提交只做一件事
5. **不改源码** – 本流程不修改产品代码，只处理 Git 与上下文归档文件
