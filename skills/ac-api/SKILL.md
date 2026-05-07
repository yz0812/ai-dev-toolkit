---
name: ac-api
description: 'SKSPIOT 智慧园区物联网平台专用 OpenAPI 3.1 导出。仅手动触发；当用户要把 Service 暴露接口整理为可导入 Apifox 的 OpenAPI 3.1 JSON 文件时，使用这个 skill。'
disable-model-invocation: true
---

# Apifox - 生成 OpenAPI 3.1 导入文件

将 SKSPIOT 项目中“无 Controller、直接暴露 Service 接口”的能力整理为 **OpenAPI 3.1 JSON 文件**，供用户手动导入 Apifox。

**不要再尝试通过 apifox MCP 直接创建或更新接口。** 当前流程的目标只有一个：**快速、稳定地生成可导入文件。**

---

## 使用方法

```bash
/ac-api <需求描述>
```

**典型输入：**
- `/ac-api 把充电桩概况接口导出成 Apifox 可导入的 OpenAPI 文件`
- `/ac-api 根据 BusinessCenter4EVChargingStation 的 overviewEVChargingStation 生成 OpenAPI 3.1 JSON`
- `/ac-api 扫描这个模块，按接口逐个导出 OpenAPI 文件`

---

## 默认约定

| 项 | 默认值 |
|---|---|
| 输出根目录 | `.claude/OpenAPI` |
| 日期目录 | `YYYY-MM-DD` |
| 文件名 | `HH-MM_BusinessCenter.method.openapi.json` |
| OpenAPI 版本 | `3.1.0` |
| 请求地址 | `http://127.0.0.1:8888` |
| 请求路径 | `/json-adapter` |
| HTTP Method | `POST` |
| Content-Type | `application/json` |
| 导出粒度 | **单接口单文件** |

**注意：**
- 一个 OpenAPI 文件里只允许一个 `POST /json-adapter`
- 如果用户要导出多个业务方法，就生成多个文件
- 文件排序依赖日期目录 + 时间前缀文件名，不要改成别的格式

---

## 适用范围

只用于 **SKSPIOT 智慧园区物联网平台**，并且必须符合以下接口约定：

- **无 Controller 层**
- 类或接口上使用 `@BusinessCenterDescriptor`
- 方法上使用 `@BusinessDescriptor`
- 所有请求均使用 `POST`
- `Content-Type` 固定为 `application/json`
- 请求体统一为：

```json
{
  "bid": "<Service全限定名>.<业务方法名>",
  "params": {
    "<参数名>": {}
  },
  "passport": "{{access_token}}"
}
```

如果当前项目不符合这套规则：

- 立即停止套用本 skill
- 明确告知用户这是 **SKSPIOT 专用 skill**
- 不要硬凑 OpenAPI 文件

---

## 执行约束

- **先读后做**：先定位注解、方法签名、参数类型、返回类型，再决定如何导出
- **快速优先**：优先直接读取目标方法名、接口参数、返回类型；只有在需要展开 DTO/VO 字段时再继续追踪相关类型，已知文件/方法时不要先全量扫描整个源码树
- **禁止猜测**：不猜包名、不猜 `bid`、不猜参数名、不猜返回结构
- **必须澄清**：信息缺失、项目范围不清、接口定位不准时，用 `AskUserQuestion` 先问清楚
- **示例自动推断**：参数和返回值如果没有显式示例或 schema，优先按真实参数/返回实体推导；证据不足时再退化为最小占位，不再硬编码通用成功对象
- **返回字段说明优先取证据**：`data` 内字段说明优先取字段注解（如 `@Schema` / `@ApiModelProperty`）和字段 Javadoc/注释，不要把自动补全文本冒充成真实字段说明
- **证据不足必须显式说明**：如果返回字段缺少注解/Javadoc/注释，允许继续导出，但必须在交付结果里明确指出哪些字段说明缺少代码证据，不能静默略过
- **类型歧义不得静默命中**：返回类型或字段类型存在重名 DTO/VO 歧义时，不要默认选第一个命中结果；必须保守降级或明确提示冲突点
- **响应固定包装**：返回值统一生成为 `{ "code": "success", "success": true, "data": <返回实体>, "msg": "操作成功" }`，其中 `data` 基于接口真实返回实体推导
- **禁止声称已同步到 Apifox**：这里只生成导入文件，不直接写入 Apifox
- **优先脚本生成**：OpenAPI JSON 由本地脚本生成，不要让大模型直接手写大段 OpenAPI 文档
- **禁止回读脚本与产物**：正常执行时，不要回读 `generate_openapi.py`、`export_openapi_from_java.py`，也不要在生成后再回读 `.openapi.json` / `.metadata.json`；只有在调试 skill 本身时才允许这样做
- **最小产物原则**：优先生成可导入、可读、可排序的 JSON 文件，不额外扩展复杂字段
- **单接口单文件**：不要把多个业务方法塞进同一个 OpenAPI 文件

---

## 必须先确认的事项

遇到以下情况，先提问，不要直接执行：

| 场景 | 必须确认的问题 |
|---|---|
| 用户只说“导出接口” | 要导出哪个 Service、哪个方法、哪个模块？ |
| 用户要批量导出 | 是逐个方法分别生成多个文件，还是先只导出其中几个关键接口？ |
| `@BusinessDescriptor.name` 与方法名不一致 | `bid` 最后一级到底取哪个？ |

---

## 识别规则

### 1. 识别业务中心

优先定位类或接口上的 `@BusinessCenterDescriptor`，确认这是对外暴露的业务中心。

### 2. 识别具体接口

在业务中心内定位方法上的 `@BusinessDescriptor`，至少提取以下信息：

| 字段 | 来源 |
|---|---|
| 业务中心类/接口全限定名 | Java 声明位置 |
| 业务中心短名 | 类名或接口名 |
| 方法名 | Java 方法签名 |
| 业务方法名 | `@BusinessDescriptor.name`，若缺失再回退到方法名 |
| 接口说明 | `@BusinessDescriptor.desc` |
| 返回说明 | `@BusinessDescriptor.returnDesc` |
| 参数列表 | Java 方法参数名 + 参数类型 |
| 返回类型 | Java 方法返回类型 |
| 字段中文说明 | 字段注解 > 字段注释/Javadoc；无证据时明确标记缺口，不把自动补全当成真实说明 |
| 证据 | `file_path:line_number` |

### 3. `bid` 生成规则

`bid` 由两段组成：

1. **Service 暴露接口的全限定名**
2. **业务方法名**

格式：

```text
<serviceFqcn>.<businessMethod>
```

示例：

```text
base.business.energy.service.BusinessCenter4EVChargingStation.overviewEVChargingStation
```

**注意：**
- 优先使用 **对外暴露的 Service 接口/业务中心定义**，不要误用实现类
- 方法段优先取 `@BusinessDescriptor.name`
- 如果 `@BusinessDescriptor.name` 缺失，再使用 Java 方法名
- 如果注解值、方法名、现有调用样例彼此冲突，必须停下来询问用户，不要猜

### 4. 请求体组装规则

请求统一使用：

- Method：`POST`
- URL：`http://127.0.0.1:8888/json-adapter`
- Header：`Content-Type: application/json`

请求体固定外层结构：

```json
{
  "bid": "<serviceFqcn>.<businessMethod>",
  "params": {
    "<参数名>": {}
  },
  "passport": "{{access_token}}"
}
```

`params` 的规则：

- **单参数方法**：保留参数名，不要省略外层键
- **多参数方法**：按方法参数名逐个展开为 key
- **无参数方法**：使用空对象 `{}`
- **示例值**：优先从现有代码、示例请求、测试、文档中提取；没有证据就按参数名和类型自动推断合理默认值

---

## 生成脚本

统一使用本地脚本：

```bash
python skills/ac-api/scripts/generate_openapi.py --input <metadata.json>
python skills/ac-api/scripts/export_openapi_from_java.py --source <Java文件或目录> --save-metadata
```

也支持 **stdin + 自动落 metadata**：

```bash
python skills/ac-api/scripts/generate_openapi.py --input - --save-metadata <<'EOF'
{
  "serviceFqcn": "base.business.energy.service.BusinessCenter4EVChargingStation",
  "serviceName": "BusinessCenter4EVChargingStation",
  "methodName": "overviewEVChargingStation",
  "businessMethod": "overviewEVChargingStation",
  "summary": "充电桩概况",
  "description": "充电桩概况",
  "returnType": "EVOverviewEVChargingStationDTO",
  "returnDesc": "EvChargingStationPowerDataStatistics",
  "parameters": [
    {
      "name": "vo",
      "type": "EVSPageRspVO",
      "example": {
        "projectId": 1
      }
    }
  ],
  "responseExample": {},
  "evidence": [
    "src/main/java/.../BusinessCenter4EVChargingStation.java:42"
  ]
}
EOF
```

开启 `--save-metadata` 后，脚本会在同目录额外写出一个 `.metadata.json`，方便追溯来源。

### 元数据文件格式

在调用脚本前，先整理一个**小型元数据 JSON**，再交给脚本生成最终 OpenAPI 文件。

最小示例：

```json
{
  "serviceFqcn": "base.business.energy.service.BusinessCenter4EVChargingStation",
  "serviceName": "BusinessCenter4EVChargingStation",
  "methodName": "overviewEVChargingStation",
  "businessMethod": "overviewEVChargingStation",
  "summary": "充电桩概况",
  "description": "充电桩概况",
  "returnType": "EVOverviewEVChargingStationDTO",
  "returnDesc": "EvChargingStationPowerDataStatistics",
  "parameters": [
    {
      "name": "vo",
      "type": "EVSPageRspVO",
      "example": {
        "projectId": 1
      }
    }
  ],
  "responseExample": {},
  "evidence": [
    "src/main/java/.../BusinessCenter4EVChargingStation.java:42"
  ]
}
```

### 脚本输出规则

脚本会自动生成：

| 项 | 规则 |
|---|---|
| 输出目录 | `.claude/OpenAPI/YYYY-MM-DD/` |
| 文件名 | `HH-MM_BusinessCenter.method.openapi.json` |
| metadata 文件 | `HH-MM_BusinessCenter.method.metadata.json`（仅 `--save-metadata` 时生成） |
| `openapi` | `3.1.0` |
| `servers[0].url` | `http://127.0.0.1:8888` |
| `paths` | 只生成一个 `/json-adapter` |
| `operationId` | `BusinessCenter.method` |

如果用户明确要求时间戳一致，可在同一轮导出时复用同一个分钟值。

---

## 推荐执行流程（硬性 4 步）

### 步骤 1：确认范围

先确认目标是哪个 Service、哪个方法、哪个模块。

- 单接口：直接继续
- 多接口：明确告诉用户会生成多个 **单接口单文件**
- 范围不清：先提问，不要猜

### 步骤 2：读取必要代码

只读取当前接口生成所必需的代码证据：

- `@BusinessCenterDescriptor` 所在类/接口
- `@BusinessDescriptor` 所在方法
- 方法签名
- 必要的参数类型与返回类型定义

约束：

- 已知文件路径：直接读目标文件
- 已知类名/方法名：精确定位后读取
- 只在需要展开字段时继续追踪 DTO / VO
- **正常执行禁止回读 skill 自带脚本和既有生成产物**

### 步骤 3：整理 metadata 并立即生成

整理最小 metadata 后，直接调用脚本生成，不做额外往返检查。

最小 metadata 至少包含：

| 项 | 内容 |
|---|---|
| `serviceFqcn` | Service 全限定名 |
| `serviceName` | Service 短名 |
| `methodName` | Java 方法名 |
| `businessMethod` | `@BusinessDescriptor.name` 或方法名 |
| `summary` | 业务描述 |
| `description` | 业务描述或补充说明 |
| `returnType` | Java 返回类型 |
| `returnDesc` | `@BusinessDescriptor.returnDesc` |
| `parameters` | 参数名、类型、示例 |
| `responseExample` / `responseSchema` | 有则提供 |
| `evidence` | `file_path:line_number` |

推荐命令：

```bash
python skills/ac-api/scripts/generate_openapi.py --input <metadata.json> --save-metadata
```

或：

```bash
python skills/ac-api/scripts/generate_openapi.py --input - --save-metadata
```

仅当用户明确要求“直接从 Java 一条龙导出”时，才使用：

```bash
python skills/ac-api/scripts/export_openapi_from_java.py --source <Java文件或目录> --save-metadata
```

### 步骤 4：直接交付结果

执行脚本后，直接返回：

- 输出文件路径
- 是否生成 metadata
- 对应 `bid`
- 关键代码证据

不要做这些事：

- 不回读 `generate_openapi.py` / `export_openapi_from_java.py`
- 不回读刚生成的 `.openapi.json` / `.metadata.json`
- 不为了“确认一下”再绕回脚本或产物

只有在**调试 skill 本身**或**脚本报错排查**时，才允许例外。

---

## 输出要求

先给出结果摘要表：

| 项目 | 内容 |
|---|---|
| 输出文件 | `<实际文件路径>` |
| OpenAPI 版本 | `3.1.0` |
| 请求地址 | `http://127.0.0.1:8888/json-adapter` |
| 接口名称 | `<summary>` |
| `bid` | `<serviceFqcn>.<businessMethod>` |
| 证据 | `file_path:line_number` |

然后补充：

- 使用了哪些代码证据（`file_path:line_number`）
- 哪些字段是从代码推导出的
- 哪些示例值来自用户或现有样例
- 如返回 schema 只做了基础占位，要明确说明

---

## 失败处理

- 找不到 `@BusinessCenterDescriptor`：告诉用户当前代码不符合 SKSPIOT 规则，或需补充目标位置
- 找不到 `@BusinessDescriptor`：告诉用户未发现可暴露的方法，并给出已检查的位置
- 无法确认 `bid`：列出冲突点并提问
- 参数示例缺失：允许导出最小空对象，但要明确说明
- 返回字段说明缺少注解/Javadoc/注释证据：允许继续导出，但必须列出缺少说明证据的字段
- 返回类型或字段类型存在重名歧义：不得静默选中某个候选；应保守降级或明确列出冲突候选
- 返回结构无法可靠推断：允许先导出基础 schema，但要明确说明
- 脚本执行失败：原样展示错误信息，并说明失败发生在元数据还是脚本生成阶段
