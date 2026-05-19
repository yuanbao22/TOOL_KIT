# Abaqus 工具包 — PySide6 技术设计文档

## 1. 概述

### 1.1 项目定位

面向 Abaqus 有限元分析工程师的 Windows 桌面批处理工具，提供 INP 文件合并、批量提交计算、差异对比等日常效率工具。

### 1.2 架构目标

- **文件精简**：整个项目 ≤ 12 个源文件（vs 当前 WPF 方案的 35+）
- **零依赖生成代码**：无 Source Generator、无 bin/obj、无 .xaml 配对文件
- **可读性优先**：Abaqus 用户普遍掌握 Python，代码即文档
- **打包即用**：单文件 .exe（≤ 80MB），无需安装运行时

### 1.3 运行环境

| 维度 | 要求 |
|------|------|
| 操作系统 | Windows 10 / 11（64 位） |
| Python | 3.10 ~ 3.12（开发期） |
| 运行时 | PySide6（Qt for Python，官方绑定） |
| 可选依赖 | Abaqus 求解器（部分功能需要，如批量计算） |
| 分发形式 | PyInstaller 单文件 .exe（用户无须安装 Python） |

---

## 2. 技术栈

### 2.1 核心选型

| 层 | 技术 | 版本 | 选型理由 |
|---|------|------|----------|
| 开发语言 | **Python** | 3.10+ | Abaqus 脚本即 Python，工程师可直接参与维护 |
| UI 框架 | **PySide6** | 6.6+ | Qt 官方 Python 绑定，30 年成熟度，原生 Windows 控件 |
| 样式方案 | **QSS（Qt Style Sheets）** | — | CSS 语法，可实现 Fluent Design 风格 |
| 打包工具 | **PyInstaller** | 6.x | 成熟稳定，onefile 模式输出单文件 |
| 日志 | **logging**（内置） | — | Python 标准库，无需第三方依赖 |
| 测试 | **pytest** | 8.x | 事实标准，参数化测试友好 |
| INP 解析 | **逐行流式解析** | — | 生成器模式，内存友好，与 WPF 版逻辑一致 |
| 进程调用 | **subprocess**（内置） | — | 标准库，调用 Abaqus 命令行 |

### 2.2 依赖清单

```text
# requirements.txt
PySide6>=6.6,<7.0
pytest>=8.0
pytest-qt>=4.2          # Qt 界面测试
pyinstaller>=6.0
```

仅 4 个依赖包。核心运行时只依赖 PySide6。

### 2.3 与 WPF 方案的对比

| 维度 | WPF 方案（当前） | PySide6 方案 |
|------|:---:|:---:|
| 源文件数量 | ~35 个 | ~12 个 |
| 生成/中间文件 | bin/obj/.csproj/.sln/Source Generator | 无 |
| 页面文件配比 | 4 文件/页面（.xaml + .cs + VM + Service） | 1 文件/页面（UI + 逻辑） |
| 数据模型 | 每模型 1 文件（9 个 .cs） | 1 文件（`models.py`，dataclass 一行一个） |
| 用户可维护性 | 需 C# + WPF 技能 | Python 即可（Abaqus 用户通用技能） |
| 启动时间 | ~1s（JIT 编译） | ~1s |
| 打包体积 | ~70MB（含 Runtime） | ~60~80MB（含 Python 解释器） |

---

## 3. 项目结构

```
abaqus_toolkit/
├── main.py                         # 入口 + 主窗口 + 导航 + 日志配置
├── pages/
│   ├── __init__.py
│   ├── dashboard_page.py           # 仪表盘页面
│   └── merge_page.py               # INP 合并页面
├── core/
│   ├── __init__.py
│   ├── models.py                   # 所有数据模型（dataclass，共 9 个）
│   ├── inp_parser.py               # INP 文件解析器
│   ├── inp_writer.py               # INP 文件写出器（含重编号）
│   └── merge_engine.py             # 合并核心逻辑（聚合 parser + writer）
├── resources/
│   ├── icons/                      # SVG/PNG 图标
│   └── style.qss                   # QSS 全局样式表
├── tests/
│   ├── __init__.py
│   ├── test_parser.py              # 解析器单元测试
│   ├── test_writer.py              # 写出器单元测试
│   └── test_merge_engine.py        # 合并引擎集成测试
├── requirements.txt
├── build.py                        # PyInstaller 打包配置脚本
└── README.md
```

### 3.1 文件职责

| 文件 | 行数估计 | 职责 |
|------|:---:|------|
| `main.py` | ~150 | `QApplication` 入口，`QMainWindow` 主窗口，`QListWidget` 导航，`QStackedWidget` 页面切换，logging 初始化 |
| `pages/dashboard_page.py` | ~80 | 欢迎页布局：图标、标题、功能卡片 |
| `pages/merge_page.py` | ~250 | 文件选择、参数输入、执行按钮、日志输出区 |
| `core/models.py` | ~120 | 9 个 `@dataclass` + 类型别名，一行一个模型 |
| `core/inp_parser.py` | ~400 | 四阶段解析（Heading → Part → Assembly → Material/Step），各子解析器 |
| `core/inp_writer.py` | ~200 | Part/Assembly 写出，节点/单元重编号，Set 偏移 |
| `core/merge_engine.py` | ~300 | 六阶段合并流水线，Assembly 对象合并 |
| `resources/style.qss` | ~100 | QSS 样式表（Fluent 风格色板、控件美化） |

---

## 4. 数据模型

### 4.1 模型定义（`core/models.py`）

```python
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class InpNode:
    """节点 (Id, X, Y, Z)"""
    id: int
    x: float
    y: float
    z: float

@dataclass
class InpElement:
    """单元 (Id, NodeIds[])"""
    id: int
    node_ids: list[int]      # C#: int[]

@dataclass
class InpSet:
    """节点集(Nset)或单元集(Elset)，支持 generate 与显式列表"""
    name: str = ""
    is_generate: bool = False
    start: int = 0
    end: int = 0
    step: int = 0
    ids: list[int] = field(default_factory=list)

@dataclass
class InpPart:
    """一个 Part 段（*Part 到 *End Part）"""
    name: str = ""
    element_type: str = ""
    nodes: list[InpNode] = field(default_factory=list)
    elements: list[InpElement] = field(default_factory=list)
    nsets: list[InpSet] = field(default_factory=list)
    elsets: list[InpSet] = field(default_factory=list)
    solid_section_lines: list[str] = field(default_factory=list)

@dataclass
class InpInstance:
    """Assembly 中的 Instance 定义"""
    name: str = ""
    part_name: str = ""
    offset_x: float = 0.0
    offset_y: float = 0.0
    offset_z: float = 0.0
    has_offset: bool = False

@dataclass
class InpAssemblyElset:
    """Assembly 级 Elset（含 instance= 参数）"""
    name: str = ""
    instance_name: Optional[str] = None
    is_generate: bool = False
    is_internal: bool = False
    start: int = 0
    end: int = 0
    step: int = 0
    ids: list[int] = field(default_factory=list)
    keyword_line: str = ""
    data_lines: list[str] = field(default_factory=list)

@dataclass
class InpSurfaceEntry:
    """Surface 中的单个 face 条目"""
    elset_name: str = ""
    face_label: str = ""

@dataclass
class InpSurface:
    """Surface 定义"""
    name: str = ""
    type: str = ""
    entries: list[InpSurfaceEntry] = field(default_factory=list)

@dataclass
class InpCoupling:
    """Coupling 约束"""
    name: str = ""
    ref_node_set: str = ""
    surface: str = ""
    constraint_type: str = ""

@dataclass
class InpFileModel:
    """完整的 INP 文件模型"""
    heading_lines: list[str] = field(default_factory=list)
    parts: list[InpPart] = field(default_factory=list)
    assembly_name: str = ""
    assembly_instances: list[InpInstance] = field(default_factory=list)
    assembly_ref_nodes: list[InpNode] = field(default_factory=list)
    assembly_nsets: list[InpSet] = field(default_factory=list)
    assembly_elsets: list[InpAssemblyElset] = field(default_factory=list)
    assembly_surfaces: list[InpSurface] = field(default_factory=list)
    assembly_couplings: list[InpCoupling] = field(default_factory=list)
    assembly_lines: list[str] = field(default_factory=list)
    material_step_lines: list[str] = field(default_factory=list)

@dataclass
class MergeResult:
    """合并结果 DTO"""
    success: bool = False
    output_path: str = ""
    message: str = ""
    log_lines: list[str] = field(default_factory=list)
    node_offset: int = 0
    elem_offset: int = 0
```

对比 WPF 版本：9 个独立 `.cs` 文件合并为 1 个 `models.py`（约 120 行）。

---

## 5. 核心模块设计

### 5.1 INP 解析器（`core/inp_parser.py`）

**职责**：将 INP 原始文本行数组解析为 `InpFileModel` 结构化对象。

**四阶段解析流程**：

```
Phase 1: parse_heading()
  └─ 收集第一个 *Part 之前的所有行 → heading_lines

Phase 2: parse_parts()
  └─ 收集 *Part ... *End Part 之间的所有 Part
      ├─ *Node       → parse_nodes()     → part.nodes
      ├─ *Element    → parse_elements()  → part.elements
      ├─ *Nset       → parse_set()       → part.nsets
      ├─ *Elset      → parse_set()       → part.elsets
      └─ *Solid Section → 原文收集       → part.solid_section_lines

Phase 3: parse_assembly()
  └─ 收集 *Assembly ... *End Assembly 之间的所有元素
      ├─ *Instance   → parse_instance()      → assembly_instances
      ├─ *Node       → parse_nodes()         → assembly_ref_nodes
      ├─ *Nset       → parse_set()           → assembly_nsets
      ├─ *Elset      → parse_assembly_elset()→ assembly_elsets
      ├─ *Surface    → parse_surface()       → assembly_surfaces
      └─ *Coupling   → parse_coupling()      → assembly_couplings

Phase 4: parse_material_step()
  └─ 收集 *End Assembly 之后的所有行 → material_step_lines
```

**接口签名**：

```python
def parse(lines: list[str]) -> InpFileModel:
    """解析 INP 行数组为结构化模型"""
    ...

def _is_keyword(line: str, keyword: str) -> bool:
    """不区分大小写判断某行是否以 *keyword 开头"""
    ...

def _parse_parameters(line: str) -> dict[str, str]:
    """提取关键词行的参数，如 *Part, name=XXX → {'name': 'XXX'}"""
    ...
```

**关键实现细节**（与 WPF 版完全对齐）：

- 节点行解析：`idx, x, y, z` 逗号分隔，容错跳过非数据行
- 单元行解析：根据单元类型（C3D8R→8节点 / C3D4→4节点）动态确定节点数
- Set 的 `generate` 模式：`start, end, step` vs 显式 ID 列表
- 注释行（`**` 开头）及空行自动跳过
- 错误处理：数据行不够→跳过该元素，不抛异常（工程文件容错优先）

### 5.2 INP 写出器（`core/inp_writer.py`）

**职责**：将结构化 `InpPart` / `InpFileModel` 写回 INP 文本格式，支持节点/单元重编号。

**接口签名**：

```python
def write_part(part: InpPart, node_offset: int = 0, elem_offset: int = 0) -> list[str]:
    """写出单个 Part 段为文本行数组，支持 ID 偏移重编号"""
    ...

def format_node_line(id: int, x: float, y: float, z: float) -> str:
    """格式化节点行：'id, x, y, z'"""
    ...

def format_element_line(id: int, node_ids: list[int]) -> str:
    """格式化单元行：'id, n1, n2, n3, ...'"""
    ...

def write_id_lines(ids: list[int]) -> list[str]:
    """写出 ID 列表，每行最多 16 个，单值行尾加逗号"""
    ...

def format_double(value: float) -> str:
    """输出干净浮点数（无多余尾零，如 2.5 而非 2.500000）"""
    ...
```

**写出顺序**（与 INP 规范对齐）：

```
*Part, name=XXX
*Node
...节点数据（已重编号）
*Element, type=C3D8R
...单元数据（已重编号）
*Nset, nset=XXX
...节点集数据
*Elset, elset=XXX
...单元集数据
*Solid Section, elset=XXX, material=XXX
...截面数据
*End Part
```

### 5.3 合并引擎（`core/merge_engine.py`）

**职责**：聚合 parser + writer，执行完整的 INP 合并流水线。

**六阶段流水线**：

```
Phase 1: 读取 + 解析 Job-1，计算偏移量
  ├─ 读取 lines1 → parse()
  ├─ 记录所有 Part 名称 → existing_names
  └─ 计算 node_offset = max(part.nodes.id), elem_offset = max(part.elements.id)

Phase 2: 写出 Job-1 的 Heading
  └─ 逐行写出 model1.heading_lines

Phase 3: 写出 Job-1 的 Parts（原样，offset=0）
  └─ write_part(part, node_offset=0, elem_offset=0)

Phase 4: 读取 + 解析 Job-2，写出 Parts（重编号）
  ├─ 读取 lines2 → parse()
  ├─ Part 名冲突 → 加 "-2" 后缀
  └─ write_part(part, node_offset, elem_offset)

Phase 5: 写出合并后的 Assembly
  ├─ Instances: Job-1 全量 + Job-2 全量（part 名冲突则映射到重命名后的名称）
  ├─ Reference Nodes: 合并两份（Job-2 节点 +offset）
  ├─ Nsets: 合并两份（重名加 _N 后缀，Job-2 ID +offset）
  ├─ Elsets: 合并两份（重名加 _N 后缀，保持 keyword_line/data_lines）
  ├─ Surfaces: 合并两份（重名加 _N 后缀，Elset 引用映射到重命名后的名称）
  └─ Couplings: 合并两份（重名加 _N 后缀，Surface/Nset 引用映射）

Phase 6: 写出 Job-1 的 Material + Step
  └─ 逐行写出 model1.material_step_lines
```

**接口签名**：

```python
class MergeEngine:
    """INP 文件合并引擎"""

    def __init__(self, log_callback=None):
        """log_callback: Callable[[str], None]，用于进度报告"""

    async def merge(
        self,
        file1_path: str,
        file2_path: str,
        output_path: str,
    ) -> MergeResult:
        """
        合并两个 INP 文件为一个。
        - 异步执行（IO 密集）
        - 通过 self.log_callback 实时报告进度
        """
        ...
```

**关键实现细节**：

| 阶段 | 处理 | 示例 |
|------|------|------|
| Part 名冲突 | 加 `-2` 后缀 | `Part-1` + `Part-1` → `Part-1-2` |
| Instance 映射 | part 名冲突→映射到重命名后的 part | `*Instance, name=Inst, part=Part-1-2` |
| Nset 名冲突 | 加 `_{count}` 后缀 | `Set-1` 重复 → `Set-1_2` |
| Elset 名冲突 | 同 Nset | `_s_Surf-1_S1` 重复 → `_s_Surf-1_S1_2` |
| Surface 名冲突 | 同 Nset | 内部的 Elset 引用也映射到新名称 |
| Coupling 名冲突 | 同 Nset | surface= 和 ref node= 参数也映射 |
| Node/Element ID | Job-2：原 ID + offset | Job-1 最大 ID=891 → Job-2 节点从 892 开始 |

---

## 6. UI 设计

### 6.1 整体布局

```
┌──────────────────────────────────────────────────────────┐
│  Abaqus 工具包                                    ─ □ × │
├────────────┬─────────────────────────────────────────────┤
│            │                                              │
│  📊 首页   │         当前页面内容区                        │
│            │                                              │
│  🔗 合并   │                                              │
│            │                                              │
│  📋 对比   │                                              │
│            │                                              │
│  ⚙ 重编号 │                                              │
│            │                                              │
│  🚀 提交   │                                              │
│            │                                              │
│            │                                              │
├────────────┴─────────────────────────────────────────────┤
│  状态栏：Ready                                            │
└──────────────────────────────────────────────────────────┘
```

**主窗口结构**（`main.py`）：

```python
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Abaqus 工具包")
        self.resize(1200, 800)

        # 左侧导航
        self.nav_list = QListWidget()
        self.nav_list.addItem("首页")
        self.nav_list.addItem("INP 合并")
        # ... 更多页面

        # 右侧页面区（QStackedWidget）
        self.pages = QStackedWidget()
        self.pages.addWidget(DashboardPage())
        self.pages.addWidget(MergePage())

        # 布局
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.nav_list)
        splitter.addWidget(self.pages)

        # 状态栏
        self.status = QStatusBar()
        self.status.showMessage("Ready")

        # 信号连接
        self.nav_list.currentRowChanged.connect(self.pages.setCurrentIndex)
```

**关键设计决策**：

- **不使用 QML**：避免引入声明式 UI 语言，保持全部逻辑在 Python 中
- **不使用 .ui 文件**（Qt Designer）：手工代码布局更灵活，避免二进制 .ui 文件污染仓库
- **页面自包含**：每个页面是一个 `QWidget` 子类，UI 构造 + 事件绑定 + 业务调用全部在一个文件中

### 6.2 仪表盘页面（`pages/dashboard_page.py`）

```
┌──────────────────────────────────────────┐
│                                          │
│              🏠 (图标)                    │
│                                          │
│      欢迎使用 Abaqus 工具包               │
│   Abaqus INP 文件管理专业工具集           │
│                                          │
│  ┌─────────────────────────────────┐     │
│  │  快捷操作                        │     │
│  │                                   │     │
│  │  [🔗] INP 合并  →  合并两个 INP   │     │
│  │  [📋] 差异对比  →  结构化差异展示 │     │
│  │  [⚙] 重编号    →  节点/单元重编号 │     │
│  │  [🚀] 批量提交  →  排队计算      │     │
│  └─────────────────────────────────┘     │
│                                          │
└──────────────────────────────────────────┘
```

**实现要点**：

- 页面顶部：居中的 QLabel 显示标题
- 快捷操作：QGroupBox 或带样式的 QFrame，内部 QVBoxLayout 排列 QPushButton 卡片
- 每个按钮点击时通过信号通知 MainWindow 切换到对应页面

```python
class DashboardPage(QWidget):
    page_change_requested = Signal(int)  # 请求切换到第 N 个页面

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        # 图标 + 标题
        icon_label = QLabel()
        icon_label.setPixmap(QPixmap("resources/icons/app.png").scaled(80, 80))
        title = QLabel("欢迎使用 Abaqus 工具包")
        subtitle = QLabel("Abaqus INP 文件管理专业工具集")

        # 快捷操作卡片
        card = QGroupBox("快捷操作")
        for label, icon, target in [
            ("INP 合并", "merge", 1),
            ("差异对比", "diff", None),
            ("重编号", "renumber", None),
            ("批量提交", "batch", None),
        ]:
            btn = QPushButton(f"  {label}")
            btn.clicked.connect(lambda checked, t=target: self._on_click(t))
            card_layout.addWidget(btn)

    def _on_click(self, target):
        if target:
            self.page_change_requested.emit(target)
```

### 6.3 INP 合并页面（`pages/merge_page.py`）

```
┌──────────────────────────────────────────────────────────┐
│  INP 文件合并                                             │
│  将两个 INP 文件合并为一个，自动处理节点和单元编号冲突。     │
│                                                           │
│  ┌───────────────────────────────────────────────────┐    │
│  │ 文件选择                                           │    │
│  │                                                    │    │
│  │ Job-1（主文件）： [_____________________] [浏览]    │    │
│  │ Job-2（次文件）： [_____________________] [浏览]    │    │
│  │ 输出文件：       [_____________________] [浏览]    │    │
│  └───────────────────────────────────────────────────┘    │
│                                                           │
│                                         [ 开始合并 ]       │
│                                                           │
│  ┌───────────────────────────────────────────────────┐    │
│  │ 合并日志                                           │    │
│  │ ─────────────────────────────────────────────── │    │
│  │ 读取文件 1: D:\Job-1.inp                          │    │
│  │   → 15432 行                                      │    │
│  │ 读取文件 2: D:\Job-2.inp                          │    │
│  │   → 12350 行                                      │    │
│  │ 节点偏移: 891, 单元偏移: 1200                     │    │
│  │ ...                                                │    │
│  └───────────────────────────────────────────────────┘    │
│                                                           │
│  状态：合并完成 → D:\Job-Merged.inp                        │
└──────────────────────────────────────────────────────────┘
```

**实现要点**：

```python
class MergePage(QWidget):
    def __init__(self):
        super().__init__()
        self.engine = MergeEngine(log_callback=self._on_log)

        # 文件选择区
        self.file1_edit = QLineEdit()
        self.file2_edit = QLineEdit()
        self.output_edit = QLineEdit()
        self.output_edit.setText("Job-Merged.inp")

        btn_browse1 = QPushButton("浏览")
        btn_browse1.clicked.connect(self._browse_file1)

        btn_browse2 = QPushButton("浏览")
        btn_browse2.clicked.connect(self._browse_file2)

        btn_output = QPushButton("浏览")
        btn_output.clicked.connect(self._browse_output)

        # 执行按钮
        self.merge_btn = QPushButton("开始合并")
        self.merge_btn.clicked.connect(self._on_merge)

        # 日志区
        self.log_area = QPlainTextEdit()
        self.log_area.setReadOnly(True)

        # 状态栏
        self.status_label = QLabel("就绪")

    def _browse_file1(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Job-1 INP 文件", "", "INP 文件 (*.inp);;所有文件 (*.*)")
        if path:
            self.file1_edit.setText(path)

    def _browse_file2(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Job-2 INP 文件", "", "INP 文件 (*.inp);;所有文件 (*.*)")
        if path:
            self.file2_edit.setText(path)

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "选择输出文件", "Job-Merged.inp", "INP 文件 (*.inp);;所有文件 (*.*)")
        if path:
            self.output_edit.setText(path)

    def _on_log(self, msg: str):
        """实时日志回调"""
        self.log_area.appendPlainText(msg)

    def _on_merge(self):
        """执行合并"""
        f1 = self.file1_edit.text().strip()
        f2 = self.file2_edit.text().strip()
        out = self.output_edit.text().strip()

        if not f1 or not f2:
            QMessageBox.warning(self, "提示", "请选择两个输入文件")
            return

        self.merge_btn.setEnabled(False)
        self.status_label.setText("正在合并...")
        self.log_area.clear()

        def run():
            result = asyncio.run(self.engine.merge(f1, f2, out))
            self.merge_btn.setEnabled(True)
            self.status_label.setText(
                f"合并完成 → {out}" if result.success else f"失败: {result.message}"
            )

        QThreadPool.globalInstance().start(run)
```

**线程模型说明**：

- 合并操作在 `QThreadPool` 中异步执行，避免阻塞 UI
- 日志通过 Qt 信号槽在主线程安全更新
- 不使用 `async/await` 直接绑定按钮事件（Qt 槽不支持 async）
- 合并完成后恢复按钮状态并更新状态栏

### 6.4 QSS 样式方案（`resources/style.qss`）

**设计原则**：模拟 Fluent Design 风格，以 QSS 实现为主，不做像素级还原。

```css
/* 色板 - Fluent 风格配色 */
/* #0078D4 Primary, #106EBE Dark, #EFF6FC Light */

QMainWindow {
    background-color: #F3F3F3;
}

QListWidget {
    background-color: #FFFFFF;
    border: none;
    font-size: 14px;
    min-width: 200px;
}

QListWidget::item {
    padding: 12px 20px;
    border-radius: 4px;
}

QListWidget::item:selected {
    background-color: #EFF6FC;
    color: #0078D4;
}

QListWidget::item:hover:!selected {
    background-color: #F5F5F5;
}

QGroupBox {
    font-size: 13px;
    font-weight: bold;
    border: 1px solid #E0E0E0;
    border-radius: 6px;
    margin-top: 16px;
    padding-top: 16px;
}

QPushButton {
    background-color: #0078D4;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 8px 24px;
    font-size: 13px;
}

QPushButton:hover {
    background-color: #106EBE;
}

QPushButton:pressed {
    background-color: #005A9E;
}

QPushButton:disabled {
    background-color: #CCCCCC;
}

QLineEdit, QPlainTextEdit {
    border: 1px solid #CCCCCC;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 13px;
    background-color: white;
}

QLineEdit:focus {
    border-color: #0078D4;
}

QStatusBar {
    background-color: #0078D4;
    color: white;
    font-size: 12px;
}
```

---

## 7. 日志系统

使用 Python 内置 `logging`，在 `main.py` 的 `main()` 函数中初始化：

```python
import logging
from pathlib import Path

def setup_logging():
    log_dir = Path.home() / "AppData" / "Local" / "AbaqusToolkit" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                log_dir / "abaqus-toolkit.log",
                encoding="utf-8",
            ),
        ],
    )
```

**日志级别使用规范**：

| 级别 | 场景 |
|------|------|
| `DEBUG` | 解析细节（每读到一行节点/单元） |
| `INFO` | 合并阶段开始/完成、文件路径 |
| `WARNING` | 非致命问题（跳过一个无效数据行） |
| `ERROR` | 合并失败、文件不存在 |

---

## 8. 线程与异步模型

| 场景 | 方案 | 说明 |
|------|------|------|
| INP 文件 IO | `QThreadPool` + `asyncio.run()` 包装 | 文件读取量不大（通常 <100MB），流式写出的 IO 密集操作 |
| Abaqus 进程调用 | `QProcess` | Qt 原生进程管理，信号通知完成/错误，可实时读取 stdout |
| 日志更新 | `QMetaObject.invokeMethod()` 或 Signal | 从工作线程切回主线程更新 UI |
| UI 响应 | 主线程（Qt Event Loop） | 所有 UI 操作在主线程 |

**关键原则**：

- 任何耗时 > 200ms 的操作必须放到后台线程
- 后台线程禁止直接操作 QWidget —— 必须用信号或 `QMetaObject.invokeMethod`
- 合并操作使用 `asyncio` 但不强制 —— 当前场景下顺序 IO 已足够快，异步主要为了不阻塞 UI

---

## 9. 测试策略

### 9.1 测试分层

| 层 | 工具 | 目标 |
|------|------|------|
| 单元测试 | pytest | 解析器、写出器、格式化函数 |
| 集成测试 | pytest | 合并引擎端到端（真实 INP 文件输入→输出验证） |
| UI 测试 | pytest-qt | 页面控件交互（按钮状态、文件对话框 mock） |

### 9.2 解析器测试（`tests/test_parser.py`）

```python
import pytest
from core.models import InpNode, InpElement
from core.inp_parser import parse

# 使用真实测试文件
TEST_DIR = Path("D:/sy/temp000")

@pytest.fixture(scope="module")
def job1_model():
    lines = Path(TEST_DIR / "Job-1.inp").read_text().splitlines()
    return parse(lines)

def test_parse_has_heading(job1_model):
    assert len(job1_model.heading_lines) > 0
    assert job1_model.heading_lines[0].startswith("*Heading")

def test_parse_one_part(job1_model):
    assert len(job1_model.parts) == 1

def test_parse_part_name(job1_model):
    assert job1_model.parts[0].name == "Part-1"

def test_parse_node_count(job1_model):
    assert len(job1_model.parts[0].nodes) == 891

def test_parse_first_node(job1_model):
    n = job1_model.parts[0].nodes[0]
    assert n.id == 1
    assert n.x == -40.0
    assert n.y == -2.5
    assert n.z == 20.0

def test_parse_element_type(job1_model):
    assert job1_model.parts[0].element_type == "C3D8R"

def test_parse_nset_generate(job1_model):
    nset = next(s for s in job1_model.parts[0].nsets if s.name == "Set-1")
    assert nset.is_generate
    assert nset.start == 1
    assert nset.end == 891
    assert nset.step == 1

# 空文件、异常数据测试
def test_parse_empty_input():
    model = parse([])
    assert len(model.parts) == 0
    assert len(model.heading_lines) == 0
```

### 9.3 写出器测试（`tests/test_writer.py`）

```python
def test_write_part_with_offset():
    part = InpPart(
        name="Test",
        nodes=[InpNode(1, 0, 0, 0), InpNode(2, 10, 0, 0)],
        elements=[InpElement(1, [1, 2, 3, 4])],
    )
    lines = write_part(part, node_offset=100, elem_offset=200)
    # 验证重编号
    assert any("101," in l for l in lines)       # node 1 + 100
    assert any("201," in l for l in lines[0])     # element 1 + 200
    assert any("104," in l for l in lines)        # node 4 + 100

def test_write_id_lines_single():
    lines = write_id_lines([5])
    assert lines[0] == "5,"  # 单值行尾加逗号

def test_write_id_lines_max_16():
    ids = list(range(100, 120))
    lines = write_id_lines(ids)
    assert len(lines) == 2  # 20 个 ID，每行 16 个→两行
```

### 9.4 合并引擎集成测试（`tests/test_merge_engine.py`）

```python
@pytest.mark.asyncio
async def test_merge_success(tmp_path):
    engine = MergeEngine()
    output = tmp_path / "merged.inp"
    result = await engine.merge(JOB1_PATH, JOB2_PATH, str(output))

    assert result.success
    assert output.exists()

    # 验证合并结果
    merged = output.read_text()
    assert "*Part, name=Part-1" in merged
    assert "*Part, name=Part-1-2" in merged         # 重命名
    assert "*Assembly, name=Assembly" in merged
    assert merged.count("*End Part") == 2             # 两个 Part 被正常关闭
```

---

## 10. 开发与构建

### 10.1 开发环境搭建

```bash
# 1. 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行（开发模式）
python main.py

# 4. 运行测试
pytest tests/ -v
```

### 10.2 打包配置（`build.py`）

```python
"""
PyInstaller 打包配置
运行: python build.py
输出: dist/AbaqusToolkit.exe
"""
import PyInstaller.__main__

PyInstaller.__main__.run([
    "main.py",
    "--name=AbaqusToolkit",
    "--onefile",               # 单文件输出
    "--windowed",              # 无控制台窗口
    "--icon=resources/icons/app.ico",
    "--add-data=resources/style.qss;resources",
    "--add-data=resources/icons;resources/icons",
    "--clean",
    "--noconfirm",
])
```

**打包后结构**：

```
dist/
└── AbaqusToolkit.exe     # 单文件 ~60-80MB，双击即用
```

### 10.3 版本管理

```bash
# 开发期
git tag v0.2.0-alpha

# 发布期
git tag v1.0.0
```

提交信息格式沿用原有规范：`feat: XXX` / `fix: XXX` / `refactor: XXX`

---

## 11. 功能规划与开发路线

### 11.1 第一期：骨架搭建 + INP 合并（预计 5~7 天）

| 阶段 | 内容 | 交付物 |
|------|------|--------|
| 1.1 | 创建项目结构、PySide6 项目骨架、`main.py` 主窗口+导航 | 可运行的空壳，带导航切换 |
| 1.2 | 实现 `core/models.py` 全部数据模型 | `models.py`，一行一个 dataclass |
| 1.3 | 实现 `core/inp_parser.py` 四阶段解析 + 子解析器 | 通过 parser 测试 |
| 1.4 | 实现 `core/inp_writer.py` Part/Assembly 写出 + 重编号 | 通过 writer 测试 |
| 1.5 | 实现 `core/merge_engine.py` 六阶段合并流水线 | 通过合并集成测试 |
| 1.6 | 实现 `pages/merge_page.py` 完整合并 UI | 可交互的合并页面 |
| 1.7 | 实现 `pages/dashboard_page.py` 仪表盘 | 完整的欢迎页 |
| 1.8 | 打包 + 端到端验收 | `AbaqusToolkit.exe`，用真实 INP 验收 |

### 11.2 第二期：批量提交框架（P1 优先级）

| 阶段 | 内容 |
|------|------|
| 2.1 | 实现 `core/abaqus_runner.py`：`QProcess` 调用 Abaqus 求解器 |
| 2.2 | 实现 `pages/batch_page.py`：INP 队列管理、状态监控、日志输出 |
| 2.3 | 支持多核并行计算、失败重试 |

### 11.3 第三期及之后（P2/P3）

| 功能 | 核心模块 |
|------|----------|
| INP 差异对比 | `core/inp_diff.py` + `pages/diff_page.py` |
| 节点/单元重编号 | `core/renumber.py` + `pages/renumber_page.py` |
| 关键字搜索替换 | `core/inp_search.py` + `pages/search_page.py` |
| ODB 结果提取 | `core/odb_reader.py` + `pages/odb_page.py` |

---

## 12. 从 WPF 版本迁移对照

| WPF 文件 | PySide6 替代 | 说明 |
|------|------|------|
| `App.xaml(.cs)` | `main.py` 的 `QApplication` + `MainWindow` | 入口统一 |
| `MainWindow.xaml(.cs)` | `main.py` 中的 `MainWindow` 类 | 布局在 `__init__` 中构建 |
| `MainViewModel.cs` | 不需要 | 无 MVVM，状态在页面内管理 |
| `Views/Pages/DashboardPage.xaml(.cs)` | `pages/dashboard_page.py` | 单个 QWidget 子类 |
| `ViewModels/Pages/DashboardViewModel.cs` | 不需要 | 合并到页面类 |
| `Views/Pages/InpMergePage.xaml(.cs)` | `pages/merge_page.py` | 单个 QWidget 子类 |
| `ViewModels/Pages/InpMergeViewModel.cs` | 不需要 | 合并到页面类 |
| `Services/IInpMergeService.cs` | 不需要 | Python duck typing，无需接口 |
| `Services/InpMergeService.cs` | `core/merge_engine.py` | 合并逻辑独立模块 |
| `Models/MergeResult.cs` | `core/models.py` 中的 `MergeResult` | 同一文件 |
| `AbaqusToolkit.Core/Parsing/InpParser.cs` | `core/inp_parser.py` | 直接翻译 |
| `AbaqusToolkit.Core/Parsing/InpWriter.cs` | `core/inp_writer.py` | 直接翻译 |
| `AbaqusToolkit.Core/Models/*.cs` (9 文件) | `core/models.py` (1 文件) | @dataclass 一行一个 |
| `AbaqusToolkit.Tests/*.cs` | `tests/test_*.py` | pytest |
| `Styles/` (HandyControl) | `resources/style.qss` | QSS 替代 XAML 资源 |
| DI 注册 (`App.xaml.cs`) | 不需要 | 无 DI 容器 |
| Serilog 配置 | `logging.basicConfig` | 标准库 |
| `AbaqusToolkit.csproj` | 不需要 | `pip install -r requirements.txt` |
| `.sln` | 不需要 | 一目录一项目 |

**从 35+ 文件 → 12 文件，无任何生成/中间文件。**

---

## 13. 风险与注意事项

| 风险 | 应对 |
|------|------|
| PyInstaller 打包兼容性 | 固定 Python 3.11（PyInstaller 兼容性好），使用 `--clean` 每次重新构建 |
| 大 INP 文件（>500MB）内存占用 | 解析器改为生成器模式（`yield` 逐行处理），不一次性加载全文 |
| QSS 与原生风格差距 | 接受"近似 Fluent"而非"100% 还原"，工程工具不过度追求像素级设计 |
| Abaqus 用户无 Python 环境的机率 | 打包为单文件 .exe，用户无需安装任何运行时 |

---

> 文档版本：v1.0  
> 日期：2026-05-19  
> 基于方案 A：Python + PySide6
