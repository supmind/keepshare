# PikPak API 接口实现分析文档

本文档详细分析了 `hosts/pikpak/api` 包中实现的 PikPak 后端接口。文档旨在指导开发人员理解现有实现细节，以便进行维护或扩展开发。

---

## 1. 全局配置与基础机制

### 1.1 Server Endpoints (Base URLs)
代码中定义了三个主要的服务端点（`api.go`）：
- **User Server**: `https://user.mypikpak.com` (用户认证、验证码)
- **Drive Server**: `https://api-drive.mypikpak.com` (文件管理、任务、分享、配额)
- **Referral Server**: `https://api-referral.mypikpak.com` (推广、佣金)

### 1.2 通用 Headers
几乎所有请求都包含以下 Headers：
- **Content-Type**: `application/json`
- **User-Agent**: `Mozilla/5.0 ...` (可配置，默认为 Chrome/115 Windows版)
- **Accept-Language**: `en,en-US;q=0.9`
- **X-Device-Id**: 设备的唯一标识符（见下方生成算法）
- **X-Client-Id**: 客户端标识
  - 通用 API 调用: `YNxT9w7GMdWvEOKa`
  - Web/Captcha 相关调用: `YUMx5nI8ZU8Ap8pm`

### 1.3 辅助算法实现
- **Device ID 生成 (`randomDevice`)**:
  - 逻辑: `MD5("Device." + random_uint64 + "." + timestamp_nano)`
  - 输出: 32位十六进制字符串
- **随机密码生成 (`randomPassword`)**:
  - 逻辑: 12位字符，首位大写字母，第二位数字，后10位为随机字符（字母/数字/符号）。
- **Device Sign (设备签名)**:
  - 在 `signup` 接口中使用，格式固定为：`fmt.Sprintf("wdi10.%sxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", deviceID)`

---

## 2. User Server 接口 (认证与账户)

此类接口主要处理注册、登录、密码重置等流程。

### 2.1 初始化验证码 (Captcha Init)
- **Go Function**: `signupCaptcha`, `signInCaptcha`, `resetPasswordCaptcha`
- **URL**: `POST /v1/shield/captcha/init`
- **Client ID**: `YUMx5nI8ZU8Ap8pm`
- **Body**:
  ```json
  {
    "action": "POST:/v1/auth/verification" (或 "POST:/v1/auth/signin"),
    "client_id": "YUMx5nI8ZU8Ap8pm",
    "device_id": "...",
    "meta": { "email": "..." }
  }
  ```
- **Response**: `{ "captcha_token": "..." }`

### 2.2 发送验证邮件 (Send Verification Email)
- **Go Function**: `signupSendEmail`, `resetPasswordSendEmail`
- **URL**: `POST /v1/auth/verification`
- **Headers**:
  - `x-captcha-token`: 上一步获取的 token
- **Body (注册场景)**:
  ```json
  {
    "email": "...",
    "target": "ANY",
    "usage": "REGISTER",
    "locale": "en-US",
    "client_id": "..."
  }
  ```
- **Body (重置密码场景)**:
  - `usage`: `"PASSWORD_RESET"`
  - `target`: `"USER"`
  - `selected_channel`: `2`
- **Response**: `{ "verification_id": "..." }`

### 2.3 验证邮件验证码 (Verify Code)
- **Go Function**: `signupVerifyCode`, `verifyResetCode`
- **URL**: `POST /v1/auth/verification/verify`
- **Body**:
  ```json
  {
    "verification_id": "...",
    "verification_code": "123456",
    "client_id": "..."
  }
  ```
- **Response**: `{ "verification_token": "..." }`

### 2.4 用户注册 (Sign Up)
- **Go Function**: `signup`
- **URL**: `POST /v1/auth/signup`
- **Headers**:
  - `x-device-sign`: `wdi10.<deviceID>...`
  - 其他模拟 App 的 Headers (如 `x-os-version`, `x-platform-version` 等)
- **Body**:
  ```json
  {
    "email": "...",
    "verification_code": "...",
    "verification_token": "...",
    "password": "...",
    "client_id": "..."
  }
  ```
- **Response**: 包含 `sub` (UserID), `access_token`, `refresh_token`.

### 2.5 用户登录 (Sign In)
- **Go Function**: `signIn`
- **URL**: `POST /v1/auth/signin`
- **Headers**:
  - `X-Captcha-Token`: 通过 `signInCaptcha` 获取
- **Body**:
  ```json
  {
    "username": "...",
    "password": "...",
    "client_id": "YNxT9w7GMdWvEOKa"
  }
  ```
- **Response**: `{ "access_token": "...", "refresh_token": "...", "expires_in": 3600 }`

### 2.6 刷新 Token (Refresh Token)
- **Go Function**: `RefreshToken`
- **URL**: `POST /v1/auth/token`
- **Body**:
  ```json
  {
    "client_id": "YNxT9w7GMdWvEOKa",
    "grant_type": "refresh_token",
    "refresh_token": "..."
  }
  ```
- **Response**: 新的 Access Token 和 Refresh Token。

### 2.7 重置密码 (Reset Password)
- **Go Function**: `resetPassword`
- **URL**: `POST /v1/auth/reset`
- **Body**:
  ```json
  {
    "new_password": "...",
    "verification_token": "...",
    "email": "...",
    "client_id": "..."
  }
  ```

---

## 3. Drive Server 接口 (文件与核心功能)

核心业务接口，需携带 `Authorization` Header (Bearer Token)。

### 3.1 从链接创建文件/任务 (Upload from Link)
- **Go Function**: `CreateFilesFromLink`
- **URL**: `POST /drive/v1/files`
- **Headers**: `X-Request-Id` (UUID)
- **Body**:
  ```json
  {
    "kind": "drive#file",
    "folder_type": "DOWNLOAD",
    "upload_type": "UPLOAD_TYPE_URL",
    "url": { "url": "https://example.com/file.zip" }
  }
  ```
- **Response**: `{ "task": { "id": "...", "file_id": "...", "phase": "..." } }`

### 3.2 查询任务状态 (Query Tasks)
- **Go Function**: `queryTasksStatus`
- **URL**: `GET /drive/v1/tasks`
- **Query Params**:
  - `type`: `"offline"`
  - `limit`: `"10000"`
  - `filters`: JSON 字符串 `{"id": {"in": "taskID1,taskID2"}}`
- **Response**: `{ "tasks": [ ... ] }`

### 3.3 查询子任务状态 (Query SubTasks)
- **Go Function**: `QuerySubTasksCompleteSizePercent`
- **URL**: `GET /drive/v1/task/{taskID}/statuses`
- **Query Params**: `limit=100`
- **Response**: `{ "statuses": [ { "file_size": "...", "phase": "..." } ] }`

### 3.4 批量删除文件 (Delete Files)
- **Go Function**: `DeleteFilesByIDs`
- **URL**: `POST /drive/v1/files:batchDelete`
- **Body**: `{ "ids": ["file_id_1", "file_id_2"] }`
- **Response**: `{ "task_id": "..." }`

### 3.5 获取存储配额 (Storage Quota)
- **Go Function**: `GetStorageSize`
- **URL**: `GET /drive/v1/about`
- **Response**: `{ "quota": { "limit": "...", "usage": "..." } }`

### 3.6 获取 VIP 状态 (Premium Status)
- **Go Function**: `GetPremiumExpiration`
- **URL**: `GET /drive/v1/privilege/vip`
- **Response**: `{ "data": { "expire": "RFC3339_Time", "status": "ok", "type": "..." } }`

### 3.7 兑换激活码 (Redeem)
- **Go Function**: `Redeem`
- **URL**: `POST /vip/v1/order/activation-code`
- **Body**: `{ "activation_code": "..." }`
- **Response**: 成功返回空，或包含错误信息。

### 3.8 查询外部链接状态 (Link Status)
- **Go Function**: `QueryLinkStatus`
- **URL**: `GET /drive/v1/resource/status`
- **Query Params**: `url={link}`
- **Response**: `{ "status": "OK" / "INVALID" ... }`
- **注意**: 此接口无需鉴权。

### 3.9 创建分享链接 (Create Share)
- **Go Function**: `CreateShare`
- **URL**: `POST /drive/v1/share`
- **Body**:
  ```json
  {
    "file_ids": ["..."],
    "share_to": "publiclink",
    "expiration_days": -1,
    "pass_code_option": "NOT_REQUIRED"
  }
  ```
- **Response**: `{ "share_url": "..." }`

### 3.10 获取分享状态 (Get Share Status)
- **Go Function**: `GetShareStatus`
- **URL**: `GET /drive/v1/share`
- **Query Params**: `share_id={share_id}`
- **Response**: `{ "share_status": "OK/DELETED/...", "user_info": { "user_id": "..." } }`
- **注意**: 无需鉴权。

### 3.11 获取分享统计 (Get Statistics)
- **Go Function**: `GetStatistics`
- **URL**: `GET /drive/v1/share/list`
- **Query Params**: `filters={"id": {"in": "share_id"}}`
- **Response**: `{ "data": [ { "view_count": "...", "restore_count": "..." } ] }`

### 3.12 批量删除分享 (Delete Share)
- **Go Function**: `DeleteShare`
- **URL**: `POST /drive/v1/share:batchDelete`
- **Body**: `{ "ids": ["share_id_1"] }`

---

## 4. Referral Server 接口 (推广与佣金)

主要用于主账户邀请子账户及查看佣金。

### 4.1 加入推广计划 (Join Referral)
- **Go Function**: `JoinReferral`
- **URL**: `POST /promoting/v1/join`
- **Body**: `{}`
- **Response**: `{ "id": "..." }`

### 4.2 邀请子账户 (Invite Sub-Account)
- **Go Function**: `InviteSubAccount`
- **URL**: `POST /promoting/v1/sub-account`
- **Body**: `{ "email": "..." }`

### 4.3 验证邀请 Token (Verify Invite Token)
- **Go Function**: `VerifyInviteSubAccountToken`
- **URL**: `GET /promoting/v1/sub-account/verify`
- **Query Params**: `token={token}`
- **注意**: 另有一个 POST 版本 `VerifyInviteSubAccountTokenByInviteToken`，用于不同场景，Body为 `{"token": "..."}`。

### 4.4 获取佣金概况 (Commissions Summary)
- **Go Function**: `GetCommissions`
- **URL**: `GET /promoting/v1/commissions/summary`
- **Response**: `{ "total": 0.0, "pending": 0.0, "available": 0.0 }`

### 4.5 获取邀请链接 (Get Invite Link)
- **Go Function**: `GetInviteToken`
- **URL**: `GET /promoting/v1/sub-account/invite-link`
- **Query Params**: `allow_login=true&action=get`
- **Response**: `{ "invite_token": "..." }`

---

## 5. 登录与 Token 管理流程

系统通过 `getToken` 统一管理 Token 的获取、缓存、刷新和重新登录。以下是完整流程：

### 5.1 自动 Token 获取流程 (`getToken`)

1.  **检查内存缓存**:
    - 系统首先检查内存缓存 (`api.cache`) 中是否存在该 UserID 对应的有效 Token。
    - 如果存在且未过期，直接返回 Token。
    - **Key**: `token:{UserID}`
    - **TTL**: 2 分钟

2.  **检查数据库**:
    - 如果缓存未命中，查询数据库 `pikpak_token` 表。
    - 如果 Token 存在且有效期大于当前时间 + 缓冲时间（2分钟），直接使用该 Token，并写入缓存。

3.  **尝试刷新 Token (Refresh Token)**:
    - 如果数据库中 Token 已过期（或即将过期），但存在 `refresh_token`。
    - 调用 `RefreshToken` 接口 (`POST /v1/auth/token`)。
    - **成功**: 更新数据库中的 Access Token 和 Refresh Token，并返回新 Access Token。
    - **失败**: 从数据库中删除该 Token 记录。

4.  **重新登录 (Sign In)**:
    - 如果上述步骤都无法获取有效 Token（无 Token 或刷新失败）。
    - 从 `pikpak_master_account` (主账号) 或 `pikpak_worker_account` (子账号) 表中读取邮箱和密码。
    - 调用 `CreateToken` -> `signIn` 执行完整登录流程。

### 5.2 完整登录流程 (`signIn`)

这是一个包含验证码的登录过程：

1.  **获取验证码 Token (Captcha Init)**:
    - 调用 `POST /v1/shield/captcha/init`。
    - `action`: `"POST:/v1/auth/signin"`
    - `meta`: `{ "email": "..." }`
    - 获取 `captcha_token`。

2.  **执行登录 (Sign In API)**:
    - 调用 `POST /v1/auth/signin`。
    - Header `X-Captcha-Token`: 填入上一步获取的 token。
    - Body:
      ```json
      {
        "username": "...",
        "password": "...",
        "client_id": "YNxT9w7GMdWvEOKa"
      }
      ```

3.  **结果处理**:
    - 获取 `access_token`, `refresh_token`, `expires_in`。
    - 将新 Token 信息写入数据库 `pikpak_token` 表（`Clauses(clause.OnConflict{UpdateAll: true})`）。
    - 返回 Token。

### 5.3 异常处理
- **密码为空**: 如果数据库中账号密码为空（未勾选“记住我”），返回错误，需提示用户重新输入。
- **账号/密码错误**: 如果登录接口返回账号密码错误，系统会自动清除数据库中的无效账号记录，防止死循环重试。
