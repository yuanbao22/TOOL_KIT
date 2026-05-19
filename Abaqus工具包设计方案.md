# Abaqus 工具包 — 设计方案

## 1. 概述

### 1.1 目标
开发一款 Windows 桌面应用程序，提供 Abaqus 批处理功能工具包，帮助工程师高效处理 INP 文件、批量提交计算、后处理等日常任务。

### 1.2 风格
采用 Microsoft Office / Fluent Design 现代风格，界面简洁清晰，适合工程人员日常使用。

### 1.3 运行环境
- 操作系统：Windows 10 / 11（64 位）
- 依赖：.NET 8 Runtime（可随发布包自带）
- 可选：Abaqus 求解器（部分功能需要）

---

## 2. 技术栈

### 2.1 核心选型

| 层 | 技术 | 版本 | 选型理由 |
|---|------|------|----------|
| 应用框架 | **WPF** | .NET 8 | Windows 原生桌面，直接调用 Abaqus 命令行，Process 集成，单文件发布 |
| 开发语言 | **C#** | 12.0 | 与 .NET 最佳搭配，高性能文本/正则处理 |
| UI 框架 | **WPF UI** | 3.x | 提供 Fluent Design 风格的 Ribbon、Navigation、Theme，开箱即用 |
| 架构模式 | **MVVM** | — | 业务与界面分离，便于后续扩展功能 |
| MVVM 工具包 | **CommunityToolkit.Mvvm** | 8.x | 微软官方，Source Generator 减少样板代码 |
| INP 解析 | **正则 + 流式解析** | — | INP 文件为结构化文本，逐行解析即可，无需第三方库 |
| 日志 | **Serilog** | — | 记录操作日志，方便排查问题 |

### 2.2 备选方案对比

| 备选 | 优势 | 不考虑的原因 |
|------|------|-------------|
| WinUI 3 | 更现代的 Fluent Design | 生态不成熟，第三方控件少，bug 较多 |
| Python + PySide6 | 开发快 | 打包体积大（~150MB），Office 风格不原生 |
| Tauri + React | 体积小（~10MB） | Abaqus 批处理场景下 WPF 更直接，React 生态对桌面适配较复杂 |

### 2.3 项目结构

```
AbaqusToolkit/
├── AbaqusToolkit/                     # WPF 主项目
│   ├── App.xaml / App.xaml.cs         # 应用入口
│   ├── MainWindow.xaml / .cs          # 主窗口（WPF UI 导航框架）
│   ├── Styles/                        # 全局样式与主题覆盖
│   │   └── Theme.xaml
│   ├── Views/
│   │   ├── Pages/
│   │   │   ├── DashboardPage.xaml     # 首页面板
│   │   │   ├── InpMergePage.xaml      # 功能1：INP 合并
│   │   │   └── (后续功能在此添加)
│   │   └── Controls/
│   │       └── InpPreviewControl.xaml # INP 文件预览控件（复用）
│   ├── ViewModels/
│   │   ├── MainViewModel.cs
│   │   └── Pages/
│   │       ├── DashboardViewModel.cs
│   │       └── InpMergeViewModel.cs
│   ├── Services/
│   │   ├── IInpMergeService.cs        # INP 合并接口
│   │   ├── InpMergeService.cs         # INP 合并核心实现
│   │   ├── IAbaqusRunnerService.cs    # Abaqus 求解器调用接口
│   │   └── AbaqusRunnerService.cs     # Abaqus 求解器调用实现
│   └── Models/
│       ├── InpFile.cs                 # INP 文件模型
│       ├── InpSection.cs              # INP 节段模型
│       └── MergeResult.cs             # 合并结果模型
├── AbaqusToolkit.Core/                # 可复用核心类库
│   ├── AbaqusToolkit.Core.csproj
│   ├── Parsing/
│   │   ├── InpParser.cs               # INP 文件解析器
│   │   └── InpWriter.cs               # INP 文件写出器
│   └── Models/
│       └── InpPart.cs                 # Part 模型
└── AbaqusToolkit.Tests/               # 单元测试
    ├── AbaqusToolkit.Tests.csproj
    └── Parsing/
        └── InpParserTests.cs
```

---

## 3. 功能规划

### 3.1 功能架构

```
                           ┌─────────────────────────┐
                           │   MainWindow (Ribbon)    │
                           │  WPF UI NavigationView   │
                           └──────────┬──────────────┘
                                      │
            ┌─────────────────────────┼─────────────────────────┐
            │                         │                         │
     ┌──────▼──────┐          ┌───────▼───────┐         ┌──────▼───────┐
     │  Dashboard  │          │  INP 合并     │         │  待开发功能   │
     │  首页面     │          │  Merge Inp    │         │  (功能2/3/…)  │
     └─────────────┘          └───────────────┘         └──────────────┘
```

### 3.2 功能1：INP 文件合并（第一期）

- **输入**：选择两个 INP 文件
- **合并逻辑**：
  - 合并两个文件的 `*Part` 到 `*End Part` 部分
  - 对 Part-2 的节点 / 单元重新编号（避免与 Part-1 冲突）
  - 合并构建唯一的 `*Assembly`，包含所有 Instance
  - `*Assembly` 之后的部分保留 Job-1 的内容
  - 参考节点、表面 Elset、Surface、Coupling 全部重新编号以避免冲突
- **输出**：单个合并后的 INP 文件
- **交互**：
  - 文件选择器（支持拖拽）
  - 预览合并前后的文件对比
  - 合并日志输出

### 3.3 待开发功能池（后续迭代）

| # | 功能 | 说明 |
|---|------|------|
| 2 | INP 文件差异对比 | 两个 INP 文件的结构化差异展示 |
| 3 | 批量节点/单元重编号 | 对 INP 内节点/单元重新编号 |
| 4 | 关键字搜索与替换 | 在 INP 文件中批量搜索替换关键字 |
| 5 | 批量提交 Abaqus 计算 | 多个 INP 排队提交，监控计算状态 |
| 6 | ODB 结果提取 | 从 .odb 文件提取特定结果到 CSV |
| 7 | INP 语法检查 | 基本的 INP 文件正确性校验 |
| 8 | 模板管理 | 常用 INP 模板（材料、边界条件等） |

---

## 4. 开发计划

### 4.1 第一期：骨架搭建 + INP 合并（2-3 天）

| 阶段 | 内容 | 交付物 |
|------|------|--------|
| **1.1 项目脚手架** | 创建 WPF 项目，安装 NuGet 包（WPF UI, CommunityToolkit.Mvvm, Serilog），配置主题和导航框架 | 项目骨架，能运行空壳 |
| **1.2 导航框架** | 搭建 WPF UI 的 NavigationView + Ribbon，创建 DashboardPage 和 InpMergePage 占位 | 主界面带导航 |
| **1.3 INP 解析核心** | 实现 `InpParser`：读取 INP 文件，分节（Heading / Part / Assembly / Material / Step） | 单元测试覆盖 |
| **1.4 INP 合并服务** | 实现 `InpMergeService`：合并两个 INP 文件，自动重编号，拼接 Assembly | 合并逻辑完成 |
| **1.5 UI 交互** | MergeInpPage 界面：文件选择、参数配置、执行合并、结果显示 | 完整功能页面 |
| **1.6 端到端验证** | 导入 Job-1.inp + Job-2.inp → 合并 → 输出 → 验证文件正确性 | 验收通过 |

### 4.2 第二期：批处理框架 + 功能扩展（待定）

| 阶段 | 内容 |
|------|------|
| 2.1 | 实现批量提交模块：队列管理、状态监控、日志输出 |
| 2.2 | 实现 INP 差异对比功能 |
| 2.3 | 实现模板管理功能 |
| 2.4 | 用户反馈后迭代优化 |

---

## 5. 技术要点

### 5.1 WPF UI 导航结构

```xml
<NavigationView x:Class="..."
                Frame="{Binding ElementName=RootFrame}"
                PaneDisplayMode="Left">
    <NavigationView.MenuItems>
        <NavigationViewItem Content="首页" Icon="Home" />
        <NavigationViewItem Content="INP 合并" Icon="Merge" />
        <NavigationViewItem Content="批处理" Icon="Play" />
    </NavigationView.MenuItems>
    <Frame x:Name="RootFrame" />
</NavigationView>
```

### 5.2 INP 合并处理流程

```
Job-1.inp ──┐
             ├──► InpParser.Parse() ──► Part-1 (nodes 1~891, elems 1~640)
             │                            Part-2 (nodes 892~1782, elems 641~1280)
Job-2.inp ──┘                            Assembly (4 instances, 2 constraints)
                                          │
                                          ▼
                                     InpWriter.Write(merged.inp)
```

### 5.3 关键技术决策

| 决策点 | 方案 | 说明 |
|--------|------|------|
| **导航** | WPF UI NavigationView | 左侧导航 + 右侧内容区，Office 风格 |
| **INP 解析** | 逐行正则匹配 | INP 格式固定，逐行解析足够 |
| **文件操作** | System.IO + async/await | 大文件读取时保持 UI 响应 |
| **配置持久化** | JSON (System.Text.Json) | 保存最近使用的文件路径等设置 |
| **Abaqus 调用** | System.Diagnostics.Process | 异步启动 `abaqus job=xxx` 并捕获输出流 |

---

## 6. 交付标准

### 6.1 第一期验收清单

- [ ] 应用启动正常，导航切换流畅
- [ ] 可选择两个 INP 文件并预览内容
- [ ] 合并后生成正确的新 INP 文件（节点/单元无重复编号）
- [ ] Assembly 中的 Instance / Elset / Surface / Coupling 引用正确
- [ ] 合并日志清晰展示操作过程和结果
- [ ] 异常处理完善（文件选择错误、解析错误等）
- [ ] 一键清空 / 重新选择

### 6.2 非功能性要求

- 合并 3000 行以内的 INP 文件耗时 < 1 秒
- 界面操作流畅，文件选择等异步操作不阻塞 UI
- 错误信息明确，指导用户操作
