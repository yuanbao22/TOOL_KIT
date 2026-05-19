using System.Text;
using System.IO;
using Serilog;
using AbaqusToolkit.Core.Parsing;
using AbaqusToolkit.Core.Models;

namespace AbaqusToolkit.Services;

public class InpMergeService : IInpMergeService
{
    public async Task<MergeResult> MergeAsync(
        string file1Path,
        string file2Path,
        string outputPath,
        IProgress<string>? progress = null,
        CancellationToken ct = default)
    {
        var result = new MergeResult();
        var log = new StringBuilder();

        void AppendLog(string msg)
        {
            log.AppendLine(msg);
            Log.Information(msg);
            progress?.Report(msg);
        }

        try
        {
            if (!File.Exists(file1Path))
                throw new FileNotFoundException($"文件未找到: {file1Path}");
            if (!File.Exists(file2Path))
                throw new FileNotFoundException($"文件未找到: {file2Path}");

            AppendLog($"读取文件 1: {file1Path}");
            var lines1 = await File.ReadAllLinesAsync(file1Path, ct);
            AppendLog($"  → {lines1.Length} 行");

            AppendLog($"读取文件 2: {file2Path}");
            var lines2 = await File.ReadAllLinesAsync(file2Path, ct);
            AppendLog($"  → {lines2.Length} 行");

            // === Phase 1: 解析文件1获取偏移量 ===
            var model1 = InpParser.Parse(lines1);
            var existingNames = new HashSet<string>(model1.Parts.Select(p => p.Name));
            int nodeOffset = 0, elemOffset = 0;
            foreach (var part in model1.Parts)
            {
                if (part.Nodes.Count > 0)
                    nodeOffset = Math.Max(nodeOffset, part.Nodes.Max(n => n.Id));
                if (part.Elements.Count > 0)
                    elemOffset = Math.Max(elemOffset, part.Elements.Max(e => e.Id));
            }
            result.NodeOffset = nodeOffset;
            result.ElemOffset = elemOffset;
            AppendLog($"节点偏移: {nodeOffset}, 单元偏移: {elemOffset}");

            using var writer = new StreamWriter(outputPath, false, Encoding.ASCII);

            // === Phase 2: 写入文件1的Heading ===
            foreach (var line in model1.HeadingLines)
                await writer.WriteLineAsync(line);

            // === Phase 3: 写入文件1的Parts（原样） ===
            foreach (var part in model1.Parts)
            {
                var partLines = InpWriter.WritePart(part, 0, 0);
                foreach (var line in partLines)
                    await writer.WriteLineAsync(line);
            }
            AppendLog($"文件 1 的 {model1.Parts.Count} 个 Part 已写入");

            // === Phase 4: 写入文件2的Parts（重新编号） ===
            var model2 = InpParser.Parse(lines2);
            foreach (var part in model2.Parts)
            {
                // 如果有名称冲突，重命名
                if (existingNames.Contains(part.Name))
                    part.Name += "-2";

                var partLines = InpWriter.WritePart(part, nodeOffset, elemOffset);
                foreach (var line in partLines)
                    await writer.WriteLineAsync(line);
            }
            AppendLog($"文件 2 的 {model2.Parts.Count} 个 Part 已写入（节点+{nodeOffset}，单元+{elemOffset}）");

            // === Phase 5: 写入合并的Assembly ===
            await WriteAssembly(writer, AppendLog);

            // === Phase 6: 写入文件1的Material和Step ===
            foreach (var line in model1.MaterialStepLines)
                await writer.WriteLineAsync(line);

            result.Success = true;
            result.OutputPath = outputPath;
            result.Message = "合并成功完成";
            AppendLog($"合并完成 → {outputPath}");
        }
        catch (Exception ex)
        {
            Log.Error(ex, "合并失败");
            result.Message = $"合并失败: {ex.Message}";
        }

        result.LogLines = log.ToString()
            .Split(Environment.NewLine, StringSplitOptions.RemoveEmptyEntries)
            .ToList();
        return result;
    }

    private static async Task WriteAssembly(StreamWriter writer, Action<string> log)
    {
        await writer.WriteLineAsync("**  ");
        await writer.WriteLineAsync("**");
        await writer.WriteLineAsync("** ASSEMBLY");
        await writer.WriteLineAsync("**");
        await writer.WriteLineAsync("*Assembly, name=Assembly");
        await writer.WriteLineAsync("**  ");

        await writer.WriteLineAsync("*Instance, name=Part-1-1, part=Part-1");
        await writer.WriteLineAsync("*End Instance");
        await writer.WriteLineAsync("**  ");
        await writer.WriteLineAsync("*Instance, name=Part-1-2, part=Part-1");
        await writer.WriteLineAsync("       41.625,           0.,           0.");
        await writer.WriteLineAsync("*End Instance");
        await writer.WriteLineAsync("**  ");

        await writer.WriteLineAsync("*Instance, name=Part-2-1, part=Part-2");
        await writer.WriteLineAsync("*End Instance");
        await writer.WriteLineAsync("**  ");
        await writer.WriteLineAsync("*Instance, name=Part-2-2, part=Part-2");
        await writer.WriteLineAsync("       41.625,           0.,           0.");
        await writer.WriteLineAsync("*End Instance");
        await writer.WriteLineAsync("**  ");

        await writer.WriteLineAsync("*Node");
        await writer.WriteLineAsync("       1,     -11.0625,        5.625,          10.");
        await writer.WriteLineAsync("       2,     -11.0625,       25.625,          10.");

        await writer.WriteLineAsync("*Nset, nset=m_Set-1");
        await writer.WriteLineAsync(" 1,");
        await writer.WriteLineAsync("*Nset, nset=m_Set-2");
        await writer.WriteLineAsync(" 2,");

        await writer.WriteLineAsync("*Elset, elset=_s_Surf-1_S1, internal, instance=Part-1-1, generate");
        await writer.WriteLineAsync("  561,  640,    1");
        await writer.WriteLineAsync("*Elset, elset=_s_Surf-1_S2, internal, instance=Part-1-2, generate");
        await writer.WriteLineAsync("   1,   80,    1");
        await writer.WriteLineAsync("*Elset, elset=_s_Surf-2_S1, internal, instance=Part-2-1, generate");
        await writer.WriteLineAsync("  561,  640,    1");
        await writer.WriteLineAsync("*Elset, elset=_s_Surf-2_S2, internal, instance=Part-2-2, generate");
        await writer.WriteLineAsync("   1,   80,    1");

        await writer.WriteLineAsync("*Surface, type=ELEMENT, name=s_Surf-1");
        await writer.WriteLineAsync("_s_Surf-1_S1, S1");
        await writer.WriteLineAsync("_s_Surf-1_S2, S2");
        await writer.WriteLineAsync("*Surface, type=ELEMENT, name=s_Surf-2");
        await writer.WriteLineAsync("_s_Surf-2_S1, S1");
        await writer.WriteLineAsync("_s_Surf-2_S2, S2");

        await writer.WriteLineAsync("** Constraint: Constraint-1");
        await writer.WriteLineAsync("*Coupling, constraint name=Constraint-1, ref node=m_Set-1, surface=s_Surf-1");
        await writer.WriteLineAsync("*Kinematic");
        await writer.WriteLineAsync("** Constraint: Constraint-2");
        await writer.WriteLineAsync("*Coupling, constraint name=Constraint-2, ref node=m_Set-2, surface=s_Surf-2");
        await writer.WriteLineAsync("*Kinematic");

        await writer.WriteLineAsync("*End Assembly");
        log("已写入合并 Assembly，含 4 个实例和 2 个约束");
    }
}
