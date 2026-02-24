# 后端代码审查报告

**审查日期**: 2026-02-24
**审查范围**: backend/app/
**审查目的**: 识别安全隐患、潜在问题和代码质量问题

---

## 一、安全问题（高优先级）

### 1.1 敏感信息泄露风险

| 严重程度 | 问题描述 | 位置 | 状态 |
|---------|---------|------|------|
| 🔴 严重 | JWT_SECRET_KEY 使用弱密钥示例值 | [.env:9](.env#L9) | ✅ 已修复 |
| 🔴 严重 | 数据库凭据硬编码在 .env 中 | [.env:12](.env#L12) | ✅ 已修复 |
| 🔴 严重 | SMTP 密码明文存储 | [.env:15](.env#L15) | ✅ 已修复 |
| 🟠 中等 | DEBUG 模式默认开启 | [config.py:35](app/config.py#L35) | ✅ 已修复 |
| 🟠 中等 | 全局异常处理器可能泄露堆栈信息 | [main.py:109-116](app/main.py#L109-L116) | ✅ 已修复 |

### 1.2 认证与授权问题

| 严重程度 | 问题描述 | 位置 | 状态 |
|---------|---------|------|------|
| 🔴 严重 | 验证码明文存储在数据库中 | [email_service.py](app/services/email_service.py) | ✅ 已修复 |
| 🟠 中等 | 登录失败次数无限制 | [auth_service.py](app/services/auth_service.py) | ✅ 已修复 |
| 🟠 中等 | 验证码错误次数无限制 | [email_service.py](app/services/email_service.py) | ✅ 已修复 |

### 1.3 CORS 配置问题

| 严重程度 | 问题描述 | 位置 | 状态 |
|---------|---------|------|------|
| 🟠 中等 | CORS 允许所有来源 | [config.py](app/config.py) | ✅ 已修复 |
| 🟠 中等 | allow_credentials=True 配合通配符 | [main.py](app/main.py) | ✅ 已修复 |

### 1.4 Cookie 安全配置

| 严重程度 | 问题描述 | 位置 | 状态 |
|---------|---------|------|------|
| 🟡 低 | COOKIE_SECURE 默认 False | [config.py:60](app/config.py#L60) | ✅ 已修复 |
| 🟡 低 | COOKIE_SAMESITE 设为 lax | [config.py:61](app/config.py#L61) | ✅ 已修复 |

---

## 二、潜在问题（中等优先级）

### 2.1 输入验证与防护

| 问题描述 | 位置 | 状态 |
|---------|------|------|
| 缺少请求体大小限制 | main.py | ✅ 已修复 |
| 邮件发送频率限制过松 | [email_service.py](app/services/email_service.py) | ✅ 已修复 |

### 2.2 时区与时间处理

| 问题描述 | 位置 | 状态 |
|---------|------|------|
| 混用 datetime.utcnow() 和 datetime.now(timezone.utc) | 多处 | ✅ 已修复 |

---

## 三、修复内容详情

### 第一阶段（立即修复 - 安全性）

#### 1. JWT 密钥安全增强 ([config.py](app/config.py))
- 添加密钥最小长度验证（32位）
- 添加生产环境安全检查
- 检测示例密钥和弱密码

#### 2. DEBUG 模式
- 默认值改为 `False`

#### 3. Cookie 安全配置 ([config.py](app/config.py))
- `COOKIE_SECURE` 默认改为 `True`
- `COOKIE_SAMESITE` 默认改为 `strict`

#### 4. CORS 配置 ([config.py](app/config.py), [main.py](app/main.py))
- 添加 `cors_allowed_hosts` 属性，根据环境返回不同的配置
- 添加 `PRODUCTION_ALLOWED_HOSTS` 配置项
- 生产环境必须配置允许的域名

#### 5. 请求体大小限制 ([main.py](app/main.py))
- 添加 16MB 请求体大小限制中间件

### 第二阶段（短期修复 - 稳定性）

#### 6. 验证码安全存储 ([email_service.py](app/services/email_service.py))
- 验证码使用 bcrypt 哈希存储
- 添加错误次数限制（5次后锁定24小时）
- 使用 constant-time 比较防止时序攻击

#### 7. 登录失败次数限制 ([auth_service.py](app/services/auth_service.py), [user.py](app/models/user.py))
- User 模型添加 `login_fail_count` 和 `login_locked_until` 字段
- 登录失败5次后锁定1小时
- 登录成功自动重置失败次数

#### 8. 时区统一
- 所有 `datetime.utcnow()` 替换为 `datetime.now(timezone.utc)`
- 确保时区一致性

---

## 四、代码亮点

1. ✅ 使用 bcrypt 哈希密码 - 安全性高
2. ✅ 密码强度验证完整 - 包含大小写、数字、特殊字符
3. ✅ JWT 使用双令牌机制 - access + refresh 分离
4. ✅ 异步数据库连接 - 性能良好
5. ✅ 完善的异常类设计 - 易于错误处理
6. ✅ 使用 httponly Cookie - 防止 XSS 窃取 token
7. ✅ 验证码哈希存储 - 防止泄露
8. ✅ 登录失败锁定 - 防止暴力破解

---

## 五、日志系统改进计划

### 5.1 当前问题

| 问题描述 | 位置 | 严重程度 |
|---------|------|---------|
| 无日志文件输出，仅控制台输出 | main.py:21-24 | 🟠 中等 |
| 无结构化日志格式（JSON） | main.py | 🟡 低 |
| 无日志轮转机制 | main.py | 🟡 低 |
| 无请求访问日志 | main.py | 🟠 中等 |
| 日志级别未区分环境 | main.py | 🟡 低 |

### 5.2 改进目标

1. **控制台日志**：美化输出格式，区分不同级别日志颜色
2. **文件日志**：按日期分割，保留30天日志
3. **请求日志**：记录所有HTTP请求的详细信息
4. **错误日志**：单独记录错误日志，便于问题排查
5. **敏感信息过滤**：自动过滤敏感字段（如密码、token）

### 5.3 改进内容

#### 1. 日志配置项 ([config.py](app/config.py))
- 添加 `LOG_DIR` 日志目录配置
- 添加 `LOG_LEVEL` 日志级别配置
- 添加 `LOG_MAX_DAYS` 日志保留天数
- 添加 `LOG_FILE_PREFIX` 日志文件前缀

#### 2. 日志模块 ([app/utils/logger.py])
- 创建统一日志工具模块
- 支持控制台和文件双输出
- 支持 JSON 格式日志
- 实现日志轮转（TimedRotatingFileHandler）

#### 3. 请求日志中间件 ([main.py])
- 记录请求ID、IP、方法、路径、状态码、耗时
- 记录请求体摘要（过滤敏感信息）

#### 4. 分级日志记录
- `app.log`：应用运行日志
- `error.log`：错误日志（ERROR级别及以上）
- `access.log`：访问日志

---

## 六、后续建议

### 短期改进
- [ ] 引入 Alembic 数据库迁移
- [ ] 完善测试覆盖
- [x] 添加审计日志

### 长期改进
- [ ] 引入密钥管理服务
- [ ] 添加性能指标监控
- [ ] 完善会话管理接口

---

**审查人**: Claude Code
**审查日期**: 2026-02-24
**最后更新**: 2026-02-24
