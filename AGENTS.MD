# AGENTS.md — 顶层开发规范

## 项目身份

本仓库为 **Abaqus Toolkit**（Abaqus 工具包），面向 Abaqus 有限元分析工程师的 Windows 桌面批处理工具。

主项目 `abaqus_toolkit/` 使用 **Python + PySide6** 实现。AI 编码助手在生成任何代码前，必须首先理解并遵守本规范。

---

## 技术栈（不可变）

| 层 | 技术 | 版本 | 约束 |
|---|------|------|------|
| 语言 | **Python** | 3.10+ | 不使用 3.13+ 独有语法 |
| UI 框架 | **PySide6** | 6.6+ | Qt 官方 Python 绑定，唯一 UI 框架 |
| 样式 | **QSS** | — | Qt Style Sheets，CSS 语法 |
| 打包 | **PyInstaller** | 6.x | 单文件 .exe 输出 |
| 日志 | **logging** | 内置 | Python 标准库 |
| 测试 | **pytest** | 8.x | 唯一测试框架 |

### 禁止引入

- 任何其他 GUI 框架（PyQt5/6、tkinter、wxPython、Flet 等）
- 任何 ORM（本项目不涉及数据库）
- 重型 Web 框架（Django、Flask 等）
- `asyncio` 之外的第三方异步库

---

## 项目结构

```
abaqus_toolkit/
├── main.py                    # 入口 + QMainWindow + 导航 + 日志初始化
├── pages/
│   ├── __init__.py
│   ├── dashboard_page.py      # 仪表盘页面
│   └── merge_page.py          # INP 合并页面
├── core/
│   ├── __init__.py
│   ├── models.py              # 所有数据模型（@dataclass）
│   ├── inp_parser.py          # INP 文件解析器
│   ├── inp_writer.py          # INP 文件写出器（含重编号）
│   └── merge_engine.py        # 合并核心引擎
├── resources/
│   └── style.qss              # QSS 全局样式表
├── requirements.txt           # 依赖清单
├── build.py                   # PyInstaller 打包脚本
└── tests/                     # 测试（pytest，按需创建）
```

---

## 架构原则

### 分层

```
Page (QWidget) → Core Module (Python) → Model (@dataclass)
     │                    │
     │                    └── 业务逻辑，可独立测试
     └── UI + 事件绑定，无独立 ViewModel
```

### 关键约束

1. **页面自包含**：每个页面是一个 `QWidget` 子类，UI 构造 + 事件绑定 + 业务调用全部在一个文件中
2. **页面不引用主窗口**：页面通过 `Signal` 与主窗口通信，不直接操作 `QMainWindow`
3. **Core 模块无 UI 依赖**：`core/` 下的模块不 import PySide6，仅使用标准库 + 自身模型
4. **Model 纯数据**：使用 `@dataclass`，不含业务逻辑
5. **无 DI 容器**：直接在构造函数或模块级创建依赖实例

### 页面通信模式

```python
# 页面发出信号
class MyPage(QWidget):
    page_change_requested = Signal(int)

# 主窗口连接信号
self.my_page.page_change_requested.connect(self.nav_list.setCurrentRow)
```

---

## 编码规范

### Python 命名

| 元素 | 风格 | 示例 |
|------|------|------|
| 模块（文件） | snake_case | `inp_parser.py` |
| 类 | PascalCase | `MergeEngine` |
| 函数 / 方法 | snake_case | `parse_lines()` |
| 变量 | snake_case | `node_offset` |
| 私有成员 | `_leading_underscore` | `_log_callback` |
| 常量 | UPPER_SNAKE_CASE | `MAX_PER_LINE` |

### 文件组织

- 一个模块一个主题（如 `inp_parser.py` 只管解析）
- `import` 排序：标准库 → 第三方 → 项目内部；各组内按字母排序
- 禁止 `from module import *`

### 注释规范

- 所有 public 函数/类必须有 docstring（`"""..."""`）
- 复杂业务逻辑必须有行内注释说明意图
- 禁止注释掉的死代码——删除它，git 会记住

---

## PySide6 特定规范

### 样式

- 使用 `resources/style.qss` 统一管理全局样式
- 颜色使用 Fluent Design 色板：主色 `#0078D4`，悬停 `#106EBE`，浅底 `#EFF6FC`
- 禁止在 Python 代码中硬编码样式字符串——用 QSS 或 `setProperty` + QSS 选择器

### 布局

- 使用代码布局（`QVBoxLayout` / `QHBoxLayout` / `QGridLayout`），不使用 `.ui` 文件
- 控件命名使用 `setObjectName()`，在 QSS 中通过 `#objectName` 选择器匹配

---

## 异步与线程

- 所有文件 IO 操作使用 `pathlib.Path.read_text()` / `write_text()`（同步即可，文件不大）
- 耗时操作（文件合并）在 `QThreadPool` 中执行，通过 Signal 回传结果到主线程
- 禁止后台线程直接操作 QWidget —— 必须用 Signal 或 `QMetaObject.invokeMethod()`
- Abaqus 进程调用使用 `QProcess`（Qt 原生进程管理）

---

## 错误处理

- 禁止 `except: pass`（吞异常）
- Core 模块在关键路径上抛异常，由调用方（Page）捕获并展示给用户
- 全局未处理异常在 `main.py` 的 logging 初始化中记录到日志文件

---

## 测试规范

- 测试框架使用 pytest
- 测试文件命名：`test_{被测模块}.py`
- 测试函数命名：`test_{场景}_{预期结果}`
- 测试目录 `tests/` 位于项目根下
- Core 模块的核心方法必须有测试覆盖

---

## Git 规范

### 提交信息

```
<type>: <简短描述>

<详细说明（可选）>
```

**Type 取值**：

| type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修 Bug |
| `refactor` | 重构（不改变功能） |
| `style` | 格式/样式调整 |
| `test` | 添加/修改测试 |
| `docs` | 文档变更 |
| `chore` | 构建/工具链变更 |

### 分支策略

- `main`：稳定分支，随时可交付
- `feat/{功能名}`：功能开发分支
- `fix/{问题描述}`：Bug 修复分支

---

## AI 辅助开发规则

### 请求处理优先级

1. **理解需求**：先确认用户意图，不假设
2. **读取上下文**：在编码前阅读相关文件（设计文档、已有代码、本规范）
3. **最小变更**：只改必要部分，不顺手重构无关代码
4. **保持一致性**：严格遵循现有代码风格和架构模式
5. **验证**：改动后运行 pytest、确保不破坏已有功能

### 禁止行为

- **禁止猜测**：不确定的 API、方法签名必须查证
- **禁止压制类型错误**：不引入类型不安全的 hack
- **禁止留 TODO**：代码中的 `# TODO` 必须在提交前解决或转为 Issue
- **禁止引入未审批的依赖**：新增 PyPI 包需确认必要性

### 新依赖引入流程

1. 明确包名和版本
2. 说明引入理由
3. 确认与现有依赖兼容
4. 更新 `requirements.txt`

---

## 运行与构建

### 开发运行

```bash
cd abaqus_toolkit
pip install -r requirements.txt
python main.py
```

### 运行测试

```bash
pytest tests/ -v
```

### 打包发布

```bash
python build.py
# 输出：dist/AbaqusToolkit.exe
```

---

## 项目状态

### 当前功能

| 功能 | 状态 | 说明 |
|------|:--:|------|
| 仪表盘首页 | ✅ | 欢迎页 + 快捷入口 |
| INP 文件合并 | ✅ | 两个 INP → 一个，自动重编号，合并 Assembly |

### 功能规划

| 优先级 | 功能 | 说明 |
|:--:|------|------|
| P1 | 批量提交 Abaqus 计算 | 多个 INP 排队提交，监控计算状态 |
| P2 | 关键字搜索与替换 | 在 INP 文件中批量搜索替换关键字 |
| P3 | ODB 结果提取 | 从 .odb 文件提取特定结果到 CSV |
| P3 | INP 语法检查 | 基本的 INP 文件正确性校验 |
| P3 | 模板管理 | 常用 INP 模板 |

---

## 版本记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-05-19 | 2.0 | 技术栈由 WPF/C# 迁移至 Python/PySide6，重写全部规范 |
| 2026-05-19 | 1.1 | 修正技术栈为 HandyControl 3.5.1，添加项目状态和功能规划 |
| 2026-05-19 | 1.0 | 初始版本，建立顶层规范 |
