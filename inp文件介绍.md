# Abaqus INP 文件介绍

## 1. 什么是 INP 文件

INP 文件是以 `.inp` 为后缀的 ASCII 文本文件，是 Abaqus 有限元分析软件的核心输入文件。它包含了对整个有限元模型的完整描述，是前处理器（如 Abaqus/CAE）与求解器（Abaqus/Standard 或 Abaqus/Explicit）之间传递数据的桥梁。

Abaqus 求解器直接读取 INP 文件进行分析计算。早期的有限元软件没有图形前处理器，用户只能通过编写 INP 文件来建模分析。熟练掌握 INP 文件的语法和用法，可以直接在文件中修改模型参数，比在 GUI 中操作更高效，还能实现软件界面不支持的功能。

## 2. INP 文件的基本结构

一个完整的 INP 文件由两大部分组成：

### 2.1 模型数据（Model Data）

定义有限元模型本身的几何、材料、属性等信息。**第一个 `*STEP` 之前的所有内容都属于模型数据。**

**必需的模型数据：**
- **节点（Nodes）**：模型的几何形状通过节点坐标定义
- **单元（Elements）**：单元类型和连接关系
- **材料（Material）**：材料性能定义（如弹性、塑性、密度等）
- **截面属性（Section）**：单元截面特性

**可选的模型数据：**
- 部件（Part）和装配件（Assembly）
- 实体（Instance）
- 初始条件（Initial Conditions）：初始应力、温度、速度等
- 边界条件（Boundary Conditions）
- 约束（Constraints）：多点约束、方程等
- 相互作用（Interactions）：接触定义等
- 幅值曲线（Amplitude）
- 输出控制（Output Control）
- 用户子程序（User Subroutine）

### 2.2 历程数据（History Data）

定义分析过程、载荷、输出要求等。**第一个 `*STEP` 之后的所有内容都属于历程数据。**

**必需的历程数据：**
- **分析步类型**：必须紧跟在 `*STEP` 之后，如 `*STATIC`（静力分析）、`*DYNAMIC`（动力分析）、`*FREQUENCY`（频率分析）等

**可选的历程数据：**
- 载荷（Loads）：集中力、分布力、压力等
- 边界条件（Boundary Conditions）
- 输出控制选项（Output Requests）
- 重启控制（Restart）

**分析步概念：**
- 每个分析步以 `*STEP` 开始，以 `*END STEP` 结束
- 一个 INP 文件可以包含多个分析步
- 分析步分为两类：
  - **一般分析步（General Step）**：可以是线性或非线性
  - **线性摄动分析步（Linear Perturbation Step）**：只能是线性

## 3. INP 文件的语法规则

### 3.1 行的类型

INP 文件包含三种类型的行：

| 类型 | 标识 | 说明 |
|------|------|------|
| **关键词行（Keyword Line）** | 以 `*` 开头 | 引入选项，可带参数 |
| **数据行（Data Line）** | 无特殊标识 | 提供具体数据，紧跟关键词行 |
| **注释行（Comment Line）** | 以 `**` 开头 | 注释说明，不参与计算 |

### 3.2 关键词行规则

- 必须以星号 `*` 开头
- 关键词后可跟参数，参数之间用逗号分隔
- 参数赋值使用等号 `=`，如 `*ELEMENT, TYPE=CPS4, ELSET=MySet`
- 关键词和参数**不区分大小写**
- 如果参数太多一行写不下，在行尾加逗号表示续行

### 3.3 数据行规则

- 数据行必须紧跟对应的关键词行
- 所有数据项之间必须用**英文逗号**分隔
- 每行不能超过 **256 个字符**（包括空格）
- 行尾的空格会被忽略
- 如果一行只有一个数据项，末尾也必须加逗号
- 空数据域用省略数据表示（两个逗号之间为空），Abaqus 会使用默认值 0

### 3.4 数值表示

- **整数**：`4`、`+4`、`-4`
- **浮点数**：`4.0`、`4.`、`4.0E+0`、`.4E+1`、`40.E-1` 等均有效
- **字符串**：最长 80 个字符

### 3.5 命名规则

- 集合名、面名、材料名等标签**区分大小写**（用户子程序中使用的除外）
- 长度不超过 80 个字符
- 必须以**字母或下划线**开头
- 不能包含句点（`.`）、逗号（`,`）、等号（`= `）等特殊字符
- 标签中的空格会被忽略，除非用双引号 `""` 括起来

### 3.6 重要注意事项

- **INP 文件中不应有空行**，如需空行分隔，应在行首输入 `**` 表示注释行
- 文件通常以 `*HEADING` 开头（非必需）
- 关键词、参数、集合名称不区分大小写
- 空格和制表符不影响内容解析

## 4. 常用关键词详解

### 4.1 标题

```
*HEADING
模型标题和描述信息
```

### 4.2 部件定义

```
*Part, name=部件名称
...（节点、单元、集合等数据）
*End Part
```

### 4.3 节点定义

```
*Node
节点编号, X坐标, Y坐标, Z坐标
```

示例：
```
*Node
1, 0.0, 0.0, 0.0
2, 1.0, 0.0, 0.0
3, 0.0, 1.0, 0.0
```

**节点生成关键词：**
| 关键词 | 说明 |
|--------|------|
| `*NODE` | 定义节点坐标 |
| `*NGEN` | 在直线或曲线中生成节点集 |
| `*NFILL` | 在两组节点集中填充完整节点 |
| `*NCOPY` | 通过平移、旋转、镜像生成新节点集 |

### 4.4 单元定义

```
*Element, type=单元类型
单元编号, 节点1编号, 节点2编号, 节点3编号, ...
```

示例：
```
*Element, type=CPS4
1, 1, 2, 5, 4
2, 2, 3, 6, 5
```

**单元相关关键词：**
| 关键词 | 说明 |
|--------|------|
| `*ELEMENT` | 定义单元 |
| `*ELGEN` | 基于已有单元生成新单元 |
| `*ELCOPY` | 复制生成新单元 |

### 4.5 集合定义

**节点集合（Nset）：**

连续编号：
```
*Nset, Nset=集合名称, Generate
起始编号, 结束编号, 增量
```

不连续编号：
```
*Nset, Nset=集合名称
节点1, 节点2, ..., 节点16
...（每行最多16个）
```

**单元集合（Elset）：**

连续编号：
```
*Elset, Elset=集合名称, Generate
起始编号, 结束编号, 增量
```

不连续编号：
```
*Elset, Elset=集合名称
单元1, 单元2, ..., 单元16
```

### 4.6 截面属性

```
*Solid Section, Elset=单元集合名称, Material=材料名称
截面参数（如厚度）
```

**截面相关关键词：**
| 关键词 | 说明 |
|--------|------|
| `*SOLID SECTION` | 定义实体单元截面 |
| `*SHELL SECTION` | 定义壳单元截面 |
| `*BEAM SECTION` | 定义梁单元截面 |
| `*RIGID SURFACE` | 定义接触问题中的刚性面 |

### 4.7 装配件和实体

```
*Assembly, name=装配件名称
  *Instance, name=实体名称, part=部件名称
  ...
  *End Instance
*End Assembly
```

### 4.8 面定义

```
*Surface, type=面的类型, name=面的名称
单元集合或节点集合, 面标识
```

### 4.9 材料定义

```
*Material, name=材料名称
*Elastic
弹性模量, 泊松比
*Density
密度值
*Plastic
屈服应力, 塑性应变
...
```

**材料相关关键词：**
| 关键词 | 说明 |
|--------|------|
| `*MATERIAL` | 定义材料 |
| `*ELASTIC` | 定义线弹性性质 |
| `*PLASTIC` | 定义弹塑性材料 |
| `*DENSITY` | 定义材料密度 |
| `*DAMPING` | 定义阻尼系数 |
| `*EXPANSION` | 定义热膨胀系数 |

### 4.10 边界条件

```
*Boundary
节点编号或集合, 第一个自由度, 最后一个自由度, 位移值
```

自由度编号：
- 1-3：平动（X、Y、Z 方向）
- 4-6：转动（绕 X、Y、Z 轴）

**注意**：如果边界条件施加在初始分析步中，`*Boundary` 数据块在 `*STEP` 之前；如果施加在后续分析步中，则在 `*STEP` 之后。

### 4.11 约束

| 关键词 | 说明 |
|--------|------|
| `*BOUNDARY` | 定义固定位移和转动 |
| `*EQUATION` | 定义多点线性约束关系 |
| `*MPC` | 定义多点约束 |

### 4.12 接触

| 关键词 | 说明 |
|--------|------|
| `*CONTACT PAIR` | 定义可能接触的面 |
| `*FRICTION` | 定义摩擦模型 |

### 4.13 分析步定义

```
*Step, name=分析步名称
*Static
初始增量步, 分析步时间, 最小增量步, 最大增量步
...（载荷、边界条件、输出等）
*End Step
```

**分析类型关键词：**
| 关键词 | 说明 |
|--------|------|
| `*STATIC` | 静态分析 |
| `*DYNAMIC` | 动态应力应变分析（直接积分法） |
| `*FREQUENCY` | 计算自然频率和模态形状 |
| `*MODAL DYNAMIC` | 模态叠加法动态分析 |
| `*STEADY STATE DYNAMICS` | 动态反应稳态解 |

### 4.14 载荷定义

**集中载荷：**
```
*Cload
节点编号或集合, 自由度, 载荷值
```

**分布载荷：**
```
*Dload
单元集合, 载荷类型, 载荷大小
```

### 4.15 输出控制

| 关键词 | 说明 |
|--------|------|
| `*RESTART` | 控制重启文件（*.res）的存取 |
| `*OUTPUT` | 输出请求 |
| `*FIELD` | 场输出 |
| `*HISTORY` | 历史输出 |
| `*NODE PRINT` | 节点输出 |
| `*EL PRINT` | 单元输出 |
| `*USERSUBROUTINE` | 用户子程序 |

### 4.16 初始条件

```
*Initial Conditions
...
```

可定义初始应力、应变、速度、温度等。

## 5. INP 文件完整示例

以下是一个简化的悬臂梁分析 INP 文件示例：

```
** 悬臂梁静力分析示例
*HEADING
Cantilever Beam Static Analysis

*Preprint, echo=NO, model=NO, history=NO, contact=NO

** 定义部件
*Part, name=Beam
*Node
1, 0.0, 0.0, 0.0
2, 10.0, 0.0, 0.0
3, 20.0, 0.0, 0.0
...（更多节点）

*Element, type=B31
1, 1, 2
2, 2, 3
...（更多单元）

*Nset, nset=Fixed, generate
1, 1, 1

*Nset, nset=LoadPoint
10

*Elset, elset=AllElements, generate
1, 10, 1

*Solid Section, elset=AllElements, material=Steel
,

*End Part

** 装配件
*Assembly, name=Assembly
*Instance, name=Beam-1, part=Beam
*End Instance
*End Assembly

** 材料定义
*Material, name=Steel
*Elastic
210000.0, 0.3
*Density
7800.0

** 边界条件（初始步）
*Boundary
Fixed, 1, 6

** 分析步
*Step, name=LoadStep
*Static
1.0, 1.0, 1e-05, 1.0

** 载荷
*Cload
LoadPoint, 2, -1000.0

** 输出请求
*Output, field
*Node Output
U, RF
*Element Output
S, E

*Output, history
*Node Output, nset=LoadPoint
U

*End Step
```

## 6. 如何生成和运行 INP 文件

### 6.1 生成方式

1. **通过 Abaqus/CAE 生成**：
   - 在 Job 模块中创建作业
   - 点击 "Write Input" 按钮
   - 系统会在当前目录生成 `.inp` 文件

2. **手动编写**：
   - 使用任意文本编辑器（如 Notepad++、VS Code 等）
   - 按照语法规则直接编写

3. **通过 Python 脚本生成**：
   - 使用 Abaqus Python API 自动化建模

### 6.2 运行方式

**命令行运行：**
```bash
abaqus job=文件名 input=文件名.inp
```

**通过 Abaqus/CAE：**
- 在 Job 模块中提交作业运行

### 6.3 导入 INP 文件

在 Abaqus/CAE 中：
- 主菜单：File > Import > Model
- 选择 `.inp` 文件
- 注意：导入后只能基于网格进行修改，会丢失原始 CAD 几何体

## 7. 从外部文件引入数据

可以使用 `INPUT` 参数引用外部文件：

```
*Node, input=nodes.inp
*Element, type=CPS4, input=elements.inp
```

**注意**：使用 `INPUT` 参数时，文件名必须包含扩展名。

## 8. 查询关键词用法

完整的关键词参考手册：
- **Abaqus Keywords Reference Guide**：查询每个关键词的详细用法、参数说明和数据行格式
- **Abaqus Analysis User's Guide**：第 1.2.1 节 "Input syntax rules" 和第 1.3.1 节 "Defining a model in Abaqus"

在帮助文档中查询关键词时，会显示：
- **Level**：该关键词可以出现的位置（Part、Instance、Assembly、Model、Step）
- **Required parameters**：必需参数
- **Optional parameters**：可选参数
- **Data line**：数据行格式说明

## 9. 常见问题和注意事项

1. **逗号使用**：必须使用英文逗号 `,`，不能使用中文逗号或空格
2. **空行问题**：INP 文件中不应有空行，否则可能导致分析错误
3. **字符限制**：每行不超过 256 个字符
4. **集合名称**：每行数据行中节点或单元编号不超过 16 个
5. **文件编码**：仅支持 7 位 ASCII 字符
6. **行结束符**：需要换行符（line feed）
7. **参数顺序**：某些关键词有严格的顺序要求，如 `*STATIC` 必须跟在 `*STEP` 之后

## 10. 总结

INP 文件是 Abaqus 有限元分析的核心，掌握其结构和语法可以：
- 更高效地修改模型参数
- 实现 GUI 不支持的高级功能
- 自动化批量分析
- 深入理解有限元模型的底层定义

建议结合 Abaqus 官方帮助文档和实际案例进行学习实践。
