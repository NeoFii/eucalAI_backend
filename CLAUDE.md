# Git 开发规范

## 一、分支策略

### 核心原则

- `main` 为生产分支，**禁止直接 push**，只接受 PR 合入
- `develop` 为日常集成分支，所有功能从此切出，完成后合回
- 功能分支生命周期短，合并后立即删除

### 分支流向

```
日常开发：develop → feat/xxx  → PR → develop
发布上线：develop             → PR → main（打 tag）
紧急修复：main    → hotfix/xxx → PR → main + develop
```

### 分支命名规范

| 前缀            | 用途                   | 示例                           |
| ------------- | ---------------------- | ------------------------------ |
| `feat/`       | 新功能开发             | `feat/user-login`              |
| `fix/`        | 非紧急 bug 修复        | `fix/order-calc-error`         |
| `hotfix/`     | 生产环境紧急修复       | `hotfix/payment-crash`         |
| `refactor/`   | 重构，不改变行为       | `refactor/auth-module`         |
| `perf/`       | 性能优化               | `perf/db-query-optimize`       |
| `test/`       | 补充测试               | `test/user-service-unit`       |
| `docs/`       | 文档变更               | `docs/api-readme`              |
| `chore/`      | 构建/依赖/配置等杂项   | `chore/upgrade-webpack`        |
| `ci/`         | CI/CD 流程变更         | `ci/add-lint-check`            |
| `revert/`     | 回滚某次提交           | `revert/feat-user-login`       |
| `release/`    | 发布准备               | `release/v1.2.0`               |
| `experiment/` | 实验性探索，不一定合入 | `experiment/new-render-engine` |

**命名约定：**
- 全小写，用 `-` 连字符，不用下划线
- 可携带 issue 编号：`feat/42-user-login`

---

## 二、Commit 规范

### 格式

```
<类型>(<scope>): <简短描述>
```

### 示例

```
feat(auth): 新增用户登录功能
fix(order): 修复金额计算精度问题
refactor(user): 拆分用户服务模块
docs: 更新 API 接口文档
chore: 升级 webpack 到 5.0
```

### 约定

- `scope` 可选，填模块名
- 描述用动词开头，不超过 50 字
- 类型与分支前缀保持一致

---

## 三、PR 规范

### PR 标题格式

与 commit 规范保持一致：

```
feat: 新增用户登录功能
fix: 修复订单金额计算错误
hotfix: 修复支付崩溃问题
refactor: 重构认证模块
docs: 补充 API 文档
```

### PR 目标分支

| 场景     | base 分支  |
| -------- | ---------- |
| 日常开发 | `develop`  |
| 发布上线 | `main`     |
| 紧急修复 | `main`     |

### 合并方式

统一使用 **Squash and merge**，将多个 commit 压成一个，保持主干历史干净。

---

## 四、完整开发流程

### 日常功能开发

```bash
# 1. 从 develop 切出功能分支
git checkout develop
git pull origin develop
git checkout -b feat/user-login

# 2. 开发并提交
git add .
git commit -m "feat(auth): 新增用户登录功能"

# 3. 推送到远端
git push origin feat/user-login

# 4. GitHub 上创建 PR
#    base: develop ← compare: feat/user-login

# 5. Review 通过后 Squash and merge

# 6. 合并后清理分支
git checkout develop
git pull origin develop
git branch -d feat/user-login
```

### 发布上线

```bash
# develop → PR → main
# 合并后打 tag

git checkout main
git pull origin main
git tag -a v1.0.0 -m "release: v1.0.0"
git push origin v1.0.0
```

### 紧急修复（hotfix）

```bash
# 1. 从 main 切出
git checkout main
git pull origin main
git checkout -b hotfix/payment-crash

# 2. 修复并提交
git commit -m "hotfix: 修复支付崩溃问题"

# 3. PR → main，合并后打 tag

# 4. 同步到 develop
git checkout develop
git cherry-pick <commit-hash>
git push origin develop
```

---

## 五、版本 Tag 规范

遵循语义化版本 `v<主版本>.<次版本>.<补丁>`：

| 场景           | 示例     |
| -------------- | -------- |
| 首次发布       | `v1.0.0` |
| 新增功能       | `v1.1.0` |
| bug 修复       | `v1.1.1` |
| 破坏性变更     | `v2.0.0` |

---

## 六、PR 模板

> 存放于 `.github/pull_request_template.md`

```markdown
## 改动说明

简述做了什么，为什么这么做

## 改动类型

- [ ] feat 新功能
- [ ] fix bug 修复
- [ ] hotfix 紧急修复
- [ ] refactor 重构
- [ ] perf 性能优化
- [ ] test 测试
- [ ] docs 文档
- [ ] chore 杂项
- [ ] ci CI/CD 变更
- [ ] revert 回滚

## 测试情况

- [ ] 本地自测通过
- [ ] 涉及的边界 case 已验证

## 相关 issue

closes #issue编号（如有）
```

---

## 七、分支保护配置

GitHub Settings → Branches → Add classic branch protection rule

```
Branch name pattern: main

✅ Require a pull request before merging
✅ Do not allow bypassing the above settings
```

## 用户标识规范

- 数据库内部数字 ID (`user_id: int`) **一律不传递给前端**，只在内部服务间使用
- 后端面向前端的响应 schema **禁止**包含 `user_id` 字段
- 前端 API 查询用户信息统一通过 `user_uid: str`（NanoID UID 字符串）
- 内部服务间通信（internal endpoints）可以使用数字 `user_id`
- 响应中需要标识用户时，使用 `user_uid: str` 字段
- 用户前端：通过 Bearer token 鉴权，无需传递用户标识