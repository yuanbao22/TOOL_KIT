# Abaqus 工具包 — 技术方案

## 1. 项目概述

### 1.1 定位

面向 Abaqus 有限元分析工程师的 Windows 桌面批处理工具，提供 INP 文件处理、批量计算提交等日常效率功能。界面采用近似 Microsoft Office / Fluent Design 的现代风格。

### 1.2 运行环境

| 维度 | 要求 |
|------|------|
| 操作系统 | Windows 10 / 11（64 位） |
| 运行时 | 无需安装 Python — 分发单文件 .exe |
| 可选依赖 | Abaqus 求解器（批量计算等功能需要） |

### 1.3 架构原则

- **文件精简**：≤ 12 个源文件，无生成/中间文件
- **可读性优先**：Abaqus 用户普遍掌握 Python，代码即文档
- **单文件分发**：PyInstaller 打包为单个 .exe（~60-80MB），用户双击即用

---

## 2. 技术栈

| 层 | 技术 | 版本 | 选型理由 |
|---|------|------|----------|
| 开发语言 | **Python** | 3.10+ | Abaqus 脚本即 Python，工程师可直接参与维护；字符串/正则处理能力强 |
| UI 框架 | **PySide6** | 6.6+ | Qt 官方 Python 绑定，30 年成熟度，原生 Windows 控件，QSS 样式可实现 Fluent 风格 |
| 打包 | **PyInstaller** | 6.x | onefile 模式输出单文件 .exe |
| 日志 | **logging** | 内置 | Python 标准库，无需第三方依赖 |
| 测试 | **pytest** | 8.x | 事实标准 |
| INP 解析 | **逐行流式解析** | — | 无第三方依赖，按 INP 关键词行分段解析 |
| 进程调用 | **subprocess** | 内置 | 调用 Abaqus 命令行 |

### 2.1 依赖清单

```
PySide6>=6.6,<7.0      # UI 框架
pytest>=8.0             # 测试
pytest-qt>=4.2          # Qt 界面测试
pyinstaller>=6.0        # 打包
```

### 2.2 与 WPF 方案的对比

| 维度 | WPF 方案 | PySide6 方案 |
|------|:---:|:---:|
| 源文件数 | ~35 个 | **12 个** |
| 生成文件 | bin/obj/.sln/Source Generator | **0** |
| 用户可维护性 | 需 C# + WPF | **Python 即可** |
| 打包体积 | ~70MB | ~60-80MB |
| 文本处理 | 中 | **强**（原生字符串/正则/迭代器） |

---

## 3. 项目结构

```
abaqus_toolkit/
├── main.py                   # 入口 + 主窗口（导航 + 页面切换 + 日志配置）
├── pages/
│   ├── dashboard_page.py     # 仪表盘欢迎页
│   └── merge_page.py         # INP 合并交互页
├── core/
│   ├── models.py             # 所有数据模型（dataclass，10 个）
│   ├── inp_parser.py         # INP 文件解析器
│   ├── inp_writer.py         # INP 文件写出器（含重编号）
│   └── merge_engine.py       # 合并核心引擎
├── resources/
│   └── style.qss             # QSS 全局样式表（Fluent 风格）
├── tests/
│   ├── test_parser.py        # 解析器测试（31 用例）
│   ├── test_writer.py        # 写出器测试（23 用例）
│   └── test_merge_engine.py  # 合并集成测试（8 用例）
├── requirements.txt          # 4 个依赖
└── build.py                  # PyInstaller 打包脚本
```

---

## 4. 数据模型

所有模型使用 Python `@dataclass`，集中在 `core/models.py`（单文件）。

### 4.1 核心模型表

| 模型 | 字段 | 说明 |
|------|------|------|
| `InpNode` | `id, x, y, z` | 节点坐标 |
| `InpElement` | `id, node_ids[]` | 单元及连接节点 |
| `InpSet` | `name, is_generate, start, end, step, ids[]` | 节点集/单元集（支持 generate 和显式列表） |
| `InpPart` | `name, element_type, nodes[], elements[], nsets[], elsets[], solid_section_lines[]` | 一个 Part 段 |
| `InpInstance` | `name, part_name, offset_x/y/z, has_offset` | Assembly 中的 Instance |
| `InpAssemblyElset` | `name, instance_name, is_generate, start, end, step, ids[], keyword_line, data_lines[]` | Assembly 级 Elset |
| `InpSurfaceEntry` | `elset_name, face_label` | Surface 的 face 条目 |
| `InpSurface` | `name, type, entries[]` | Surface 定义 |
| `InpCoupling` | `name, ref_node_set, surface, constraint_type` | Coupling 约束 |
| `InpFileModel` | `heading_lines[], parts[], assembly_*, material_step_lines[]` | 完整 INP 文件模型 |

### 4.2 结果模型

| 模型 | 字段 | 说明 |
|------|------|------|
| `MergeResult` | `success, output_path, message, log_lines[], node_offset, elem_offset` | 合并操作结果 |

---

## 5. API 接口

### 5.1 INP 解析器（`core/inp_parser`）

```python
def parse(lines: list[str]) -> InpFileModel
```

**输入**：INP 文件的所有行（字符串数组）。

**输出**：结构化的 `InpFileModel`，包含：
- `heading_lines` — 首个 `*Part` 或 `*Assembly` 之前的所有行
- `parts` — 每个 `*Part ... *End Part` 段解析为 `InpPart`
- `assembly_instances / assembly_nsets / assembly_elsets / assembly_surfaces / assembly_couplings` — Assembly 段结构化数据
- `material_step_lines` — `*End Assembly` 之后的所有行（材料、分析步等）

**解析阶段**：
1. Heading → 2. Parts → 3. Assembly → 4. Material / Step

### 5.2 INP 写出器（`core/inp_writer`）

```python
def write_part(part: InpPart, node_offset: int = 0, elem_offset: int = 0) -> list[str]
```

**输入**：一个 `InpPart` + 可选的节点/单元编号偏移量。

**输出**：INP 格式的文本行数组，自动完成：
- 节点 ID 重编号：`node.id + node_offset`
- 单元 ID 重编号：`elem.id + elem_offset`
- 单元内节点引用重编号：`node_id + node_offset`
- Nset/Elset ID 偏移

**辅助函数**：

```python
def format_node_line(id: int, x: float, y: float, z: float) -> str
def format_element_line(id: int, node_ids: list[int]) -> str
def write_id_lines(ids: list[int]) -> list[str]
def format_double(value: float) -> str
```

### 5.3 合并引擎（`core/merge_engine`）

```python
class MergeEngine:
    def __init__(self, log_callback: Callable[[str], None] | None = None)

    async def merge(self, file1_path: str, file2_path: str, output_path: str) -> MergeResult

    def merge_sync(self, file1_path: str, file2_path: str, output_path: str) -> MergeResult
```

**六阶段合并流水线**：

| 阶段 | 操作 |
|------|------|
| Phase 1 | 读取并解析文件 1，计算最大节点/单元 ID 作为偏移量 |
| Phase 2 | 写出文件 1 的 Heading |
| Phase 3 | 写出文件 1 的 Parts（原样，offset=0） |
| Phase 4 | 读取并解析文件 2，写出 Parts（ID + offset，Part 名冲突加 "-2" 后缀） |
| Phase 5 | 写出合并后的 Assembly（Instance、Nset、Elset、Surface、Coupling 全部去重合并） |
| Phase 6 | 写出文件 1 的 Material / Step |

**冲突处理规则**：

| 冲突类型 | 处理方式 |
|------|------|
| Part 名重复 | 加 "-2" 后缀 |
| Nset / Elset 名重复 | 加 `_{序号}` 后缀 |
| Surface / Coupling 名重复 | 加 `_{序号}` 后缀，内部引用同步映射 |
| 节点/单元 ID 重叠 | Job-2 的全部 ID 加上 Job-1 的最大 ID 作为偏移 |

---

## 6. UI 界面

### 6.1 主窗口布局

```
┌──────────────────────────────────────────────┐
│  Abaqus 工具包                         ─ □ × │
├──────────┬───────────────────────────────────┤
│          │                                     │
│  📊 首页  │         当前页面内容区               │
│  🔗 合并  │                                     │
│          │                                     │
├──────────┴───────────────────────────────────┤
│  状态栏：就绪                                  │
└──────────────────────────────────────────────┘
```

- 左侧：`QListWidget` 导航栏（220px 宽）
- 右侧：`QStackedWidget` 页面容器
- 底部：`QStatusBar` 状态栏
- 样式：QSS 实现 Fluent Design 色板（主色 `#0078D4`）

### 6.2 首页（仪表盘）

- 展示应用程序图标、标题 "欢迎使用 Abaqus 工具包"
- 快捷操作卡片：点击跳转到对应功能页
- 当前仅含 **INP 合并** 快捷入口

### 6.3 INP 合并页

- **文件选择区**：Job-1（主文件）、Job-2（次文件）、输出路径，各带 "浏览" 按钮
- **执行按钮**："开始合并"，点击后异步执行（不阻塞界面）
- **日志输出区**：只读文本框，实时显示合并进度
- **状态栏**：显示 "就绪 / 合并中 / 完成 / 失败"

---

## 7. 功能列表

### 7.1 已完成功能

| 功能 | 说明 | 状态 |
|------|------|:--:|
| 仪表盘首页 | 欢迎页 + 快捷入口 | ✅ |
| INP 文件合并 | 两个 INP → 一个，自动重编号节点/单元，合并 Assembly | ✅ |

### 7.2 待开发功能

| 优先级 | 功能 | 说明 |
|:--:|------|------|
| P1 | 批量提交 Abaqus 计算 | 多个 INP 排队提交，监控计算状态 |
| P2 | 关键字搜索与替换 | 在 INP 文件中批量搜索替换关键字 |
| P3 | ODB 结果提取 | 从 .odb 文件提取特定结果到 CSV |
| P3 | INP 语法检查 | 基本的 INP 文件正确性校验 |
| P3 | 模板管理 | 常用 INP 模板（材料、边界条件等） |

---

## 8. 开发与发布

### 8.1 开发环境

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### 8.2 运行测试

```bash
pytest tests/ -v
```

当前：**62 个测试全部通过**（解析器 31 + 写出器 23 + 合并引擎 8）。

### 8.3 打包发布

```bash
python build.py
# 输出：dist/AbaqusToolkit.exe（单文件，~60-80MB）
```

用户双击 `AbaqusToolkit.exe` 即可运行，无需安装 Python 或任何运行时。

---

> 版本：v2.0  
> 日期：2026-05-19  
> 基于实现方案：Python + PySide6
