# AGENTS.md — 顶层开发规范

## 项目身份

本仓库集合所有 Abaqus 工具链项目，当前主要项目为 **Abaqus Toolkit**（WPF 桌面应用）。

所有子项目均受本文件约束。AI 编码助手在生成任何代码前，必须首先理解并遵守本规范。

---

## 技术栈（不可变）

| 层 | 技术 | 版本 | 约束 |
|---|------|------|------|
| 运行时 | **.NET** | 8.0 | 禁止使用 .NET 9+ 特性 |
| 语言 | **C#** | 12.0 | 禁止使用 C# 13 特性 |
| 桌面框架 | **WPF** | .NET 8 | 禁止引入 WinUI / WinForms |
| UI 库 | **WPF UI** | 3.x | 唯一允许的第三方 UI 框架 |
| MVVM | **CommunityToolkit.Mvvm** | 8.x | Source Generator 模式 |
| 序列化 | **System.Text.Json** | 内置 | 禁止引入 Newtonsoft.Json |
| 日志 | **Serilog** | 最新稳定版 | 统一日志门面 |
| 测试 | **xUnit** | 最新稳定版 | 单元测试首选 |
| ORM | 无 | — | 本项目不涉及数据库 |

### 禁止引入

- `Newtonsoft.Json` — 使用 `System.Text.Json`
- `AutoMapper` — 手写映射或 Source Generator
- 任何 AOP 框架（PostSharp、Castle 等）
- 任何 IOC 容器（使用 .NET 内置 DI）
- `Prism` / `Caliburn.Micro` 等重型 MVVM 框架

---

## 架构原则

### MVVM 分层

```
View (XAML) → ViewModel (C#) → Service (C#) → Model (C#)
     │              │                 │
     │              │                 └── 业务逻辑，可测试
     │              └── 状态管理，命令绑定
     └── 纯声明式，零代码后置
```

### 关键约束

1. **View 零代码**：`.xaml.cs` 文件禁止包含业务逻辑，仅允许构造函数中的 `InitializeComponent()`、`DataContext` 赋值、以及必要的导航参数接收
2. **ViewModel 不引用 View**：ViewModel 不持有任何 WPF 控件引用，不操作 `Window`、`UserControl`
3. **Service 可替换**：每个 Service 必须有接口（`IXxxService`），通过 DI 注入
4. **Model 纯数据**：Model 类为 POCO，不含业务逻辑，仅含数据属性与数据验证

### DI 注册

所有服务在 `App.xaml.cs` 的 `ConfigureServices` 中注册：

```csharp
services.AddSingleton<IMyService, MyService>();
services.AddTransient<MyViewModel>();
```

禁止在 ViewModel 中 `new` 任何 Service 实例。

---

## 项目结构规范

```
{ProjectName}/
├── {ProjectName}/                  # 主项目
│   ├── App.xaml / App.xaml.cs      # 入口 + DI 配置
│   ├── MainWindow.xaml / .cs       # 主窗口（仅导航壳）
│   ├── Styles/                     # 全局样式、主题、ResourceDictionary
│   ├── Views/
│   │   ├── Pages/                  # 导航页面（每个 NavigationViewItem 对应一个 Page）
│   │   └── Controls/               # 可复用用户控件
│   ├── ViewModels/
│   │   ├── MainViewModel.cs
│   │   └── Pages/                  # 与 Views/Pages/ 一一对应
│   ├── Services/                   # 业务服务（接口 + 实现）
│   ├── Models/                     # 数据模型（POCO）
│   └── Helpers/                    # 静态工具类（不依赖 DI 状态）
├── {ProjectName}.Core/             # 核心类库（无 UI 依赖）
│   ├── Parsing/                    # 解析器
│   └── Models/                     # 共享模型
└── {ProjectName}.Tests/            # 单元测试（一一对应 Core 结构）
```

---

## 编码规范

### C# 命名

| 元素 | 风格 | 示例 |
|------|------|------|
| 命名空间 | PascalCase | `AbaqusToolkit.Services` |
| 类 / 结构体 | PascalCase | `InpMergeService` |
| 接口 | `I` 前缀 + PascalCase | `IInpMergeService` |
| 方法 | PascalCase | `ParseAsync()` |
| 属性 | PascalCase | `FilePath` |
| 私有字段 | `_camelCase` | `_inpParser` |
| 局部变量 | camelCase | `mergeResult` |
| 常量 | PascalCase | `MaxRetryCount` |
| 异步方法 | `Async` 后缀 | `MergeAsync()` |

### XAML 命名

| 元素 | 风格 | 示例 |
|------|------|------|
| x:Name | PascalCase | `FileListBox` |
| Event Handler | `On` + 控件名 + 事件 | `OnFileSelected` |
| Style Key | 组件类型 + PascalCase | `PrimaryButtonStyle` |

### 文件组织

- 一个文件一个类（除非嵌套类或极小的相关类型）
- 文件夹结构反映命名空间层级
- `using` 排序：System → 第三方 → 项目内部；各组内按字母排序
- 禁止 `global using` 放在单个 `.cs` 文件中（统一在 `GlobalUsings.cs` 或项目配置中管理）

### 注释规范

- 所有 `public` 类和方法必须有 XML 文档注释（`<summary>`）
- 复杂业务逻辑必须有行内注释说明意图
- 禁止注释掉的死代码——删除它，git 会记住

---

## WPF 特定规范

### XAML

- 使用 `x:Name` 而非 `Name`
- Binding 显式指定 `Mode`（`OneWay` / `TwoWay` / `OneTime`）
- 禁用 `Binding` 的 `UpdateSourceTrigger=PropertyChanged` 除非确有必要（性能考虑）
- 颜色、字体、间距统一使用 `{StaticResource}` 引用，禁止硬编码
- 窗口级 `x:Class` 禁止有代码后置逻辑

### 主题

- 使用 WPF UI 提供的 Fluent Design 主题
- 自定义样式写在 `Styles/` 目录下
- 所有自定义 ResourceDictionary 在 `App.xaml` 中合并

---

## 异步与线程

- 所有 IO 操作（文件读写、进程调用）必须异步（`async/await`）
- 文件操作使用 `System.IO` 的异步 API（`ReadAllTextAsync`、`WriteAllTextAsync`）
- Abaqus 调用使用 `Process.Start` + `WaitForExitAsync`
- 禁止 `Task.Wait()` / `Task.Result` — 会导致死锁
- 禁止在工作线程直接操作 UI 元素 — 使用 `Dispatcher.InvokeAsync`

---

## 错误处理

- 禁止 `catch (Exception) { }`（吞异常）
- Service 层抛出自定义异常（如 `InpParseException`）
- ViewModel 层捕获异常，设置 `ErrorMessage` 属性，由 View 绑定显示
- 全局未处理异常在 `App.xaml.cs` 的 `DispatcherUnhandledException` 中记录

---

## 测试规范

- 测试项目使用 xUnit
- 测试文件命名：`{被测类名}Tests.cs`
- 测试方法命名：`{方法名}_{场景}_{预期结果}`（如 `Parse_EmptyFile_ReturnsEmptyList`）
- 每个 Service 的核心方法必须有测试
- 核心类库 (`*.Core`) 的测试覆盖率目标：> 80%

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
| `style` | 格式调整（空格、排序 using 等） |
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
2. **读取上下文**：在编码前阅读相关文件（设计方案、已有代码、本规范）
3. **最小变更**：只改必要部分，不顺手重构无关代码
4. **保持一致性**：严格遵循现有代码风格和架构模式
5. **验证**：改动后检查编译、运行 linter、确保不破坏已有功能

### 禁止行为

- **禁止猜测**：不确定的 API、方法签名、配置项必须查证，不可臆造
- **禁止压制类型错误**：`as any`、`@ts-ignore`、`#pragma warning disable` 一律禁止
- **禁止修改本规范文件**：AGENTS.md 的变更需项目经理审批
- **禁止引入未审批的技术栈**：所有 NuGet 包引入需对照技术栈表
- **禁止留 TODO**：代码中的 `// TODO` 必须在提交前解决或转为 Issue

### 新 NuGet 包引入流程

1. 明确包名和版本
2. 说明引入理由（不能是"常见做法"）
3. 检查与现有包的兼容性
4. 在 `AGENTS.md` 技术栈表中登记

---

## 环境配置

### 开发工具

- **IDE**：Visual Studio 2022（Community / Professional / Enterprise）
- **.NET SDK**：8.0.408（通过 `dotnet-install.ps1` 安装）
- **NuGet 源**：官方源 + 必要时企业私有源

### 本地运行

```bash
dotnet restore
dotnet build
dotnet run --project AbaqusToolkit/AbaqusToolkit.csproj
```

### 发布

```bash
dotnet publish AbaqusToolkit/AbaqusToolkit.csproj -c Release -r win-x64 --self-contained false
```

---

## 版本记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-05-19 | 1.0 | 初始版本，建立顶层规范 |
