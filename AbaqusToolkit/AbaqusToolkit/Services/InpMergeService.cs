using System.Text;
using System.Linq;
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
            await WriteAssembly(writer, model1, model2, nodeOffset, elemOffset, existingNames, AppendLog);

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

    private static async Task WriteAssembly(
        StreamWriter writer,
        InpFileModel model1,
        InpFileModel model2,
        int nodeOffset,
        int elemOffset,
        HashSet<string> renamedPartNames,
        Action<string> log)
    {
        await writer.WriteLineAsync("**  ");
        await writer.WriteLineAsync("**");
        await writer.WriteLineAsync("** ASSEMBLY");
        await writer.WriteLineAsync("**");
        await writer.WriteLineAsync("*Assembly, name=Assembly");
        await writer.WriteLineAsync("**  ");

        int instanceCount = 0;

        // === Instances from file1 ===
        foreach (var inst in model1.AssemblyInstances)
        {
            await writer.WriteLineAsync($"*Instance, name={inst.Name}, part={inst.PartName}");
            if (inst.HasOffset)
                await writer.WriteLineAsync($"       {inst.OffsetX:G}, {inst.OffsetY:G}, {inst.OffsetZ:G}");
            await writer.WriteLineAsync("*End Instance");
            await writer.WriteLineAsync("**  ");
            instanceCount++;
        }

        // === Instances from file2 (update part name if renamed) ===
        foreach (var inst in model2.AssemblyInstances)
        {
            var partName = renamedPartNames.Contains(inst.PartName) ? inst.PartName + "-2" : inst.PartName;
            await writer.WriteLineAsync($"*Instance, name={inst.Name}, part={partName}");
            if (inst.HasOffset)
                await writer.WriteLineAsync($"       {inst.OffsetX:G}, {inst.OffsetY:G}, {inst.OffsetZ:G}");
            await writer.WriteLineAsync("*End Instance");
            await writer.WriteLineAsync("**  ");
            instanceCount++;
        }

        // === Reference nodes (combined from both files) ===
        bool hasRefNodes = model1.AssemblyRefNodes.Count > 0 || model2.AssemblyRefNodes.Count > 0;
        if (hasRefNodes)
        {
            await writer.WriteLineAsync("*Node");
            foreach (var node in model1.AssemblyRefNodes)
                await writer.WriteLineAsync($"{node.Id}, {node.X:G}, {node.Y:G}, {node.Z:G}");
            foreach (var node in model2.AssemblyRefNodes)
                await writer.WriteLineAsync($"{node.Id + nodeOffset}, {node.X:G}, {node.Y:G}, {node.Z:G}");
        }

        // === Nsets from file1 ===
        var nsetNameCounts = new Dictionary<string, int>();
        foreach (var nset in model1.AssemblyNsets)
        {
            nsetNameCounts[nset.Name] = 1;
            if (nset.IsGenerate)
            {
                await writer.WriteLineAsync($"*Nset, nset={nset.Name}, generate");
                await writer.WriteLineAsync($"{nset.Start}, {nset.End}, {nset.Step}");
            }
            else
            {
                await writer.WriteLineAsync($"*Nset, nset={nset.Name}");
                await WriteIdsAsync(writer, nset.Ids.ToArray());
            }
        }

        // === Nsets from file2 (renumbered, rename duplicates) ===
        var nsetNameMap = new Dictionary<string, string>();
        foreach (var nset in model2.AssemblyNsets)
        {
            string newName = nset.Name;
            if (nsetNameCounts.ContainsKey(nset.Name))
            {
                nsetNameCounts[nset.Name]++;
                newName = $"{nset.Name}_{nsetNameCounts[nset.Name]}";
            }
            else
            {
                nsetNameCounts[nset.Name] = 1;
            }
            nsetNameMap[nset.Name] = newName;
            
            if (nset.IsGenerate)
            {
                await writer.WriteLineAsync($"*Nset, nset={newName}, generate");
                await writer.WriteLineAsync($"{nset.Start + nodeOffset}, {nset.End + nodeOffset}, {nset.Step}");
            }
            else
            {
                await writer.WriteLineAsync($"*Nset, nset={newName}");
                await WriteIdsAsync(writer, nset.Ids.Select(id => id + nodeOffset).ToArray());
            }
        }

        // === Elsets from file1 ===
        foreach (var elset in model1.AssemblyElsets)
        {
            await writer.WriteLineAsync(elset.KeywordLine);
            foreach (var dataLine in elset.DataLines)
                await writer.WriteLineAsync(dataLine);
        }

        // === Elsets from file2 (rename duplicates with suffix) ===
        var elsetNameCounts = new Dictionary<string, int>();
        var elsetNameMap = new Dictionary<string, string>(); // original name -> new name for model2
        foreach (var elset in model1.AssemblyElsets)
        {
            elsetNameCounts[elset.Name] = 1;
        }
        // First pass: write model1 elsets and count
        foreach (var elset in model1.AssemblyElsets)
        {
            await writer.WriteLineAsync(elset.KeywordLine);
            foreach (var dataLine in elset.DataLines)
                await writer.WriteLineAsync(dataLine);
        }
        // Second pass: write model2 elsets with renaming
        foreach (var elset in model2.AssemblyElsets)
        {
            string newName = elset.Name;
            if (elsetNameCounts.ContainsKey(elset.Name))
            {
                elsetNameCounts[elset.Name]++;
                newName = $"{elset.Name}_{elsetNameCounts[elset.Name]}";
            }
            else
            {
                elsetNameCounts[elset.Name] = 1;
            }
            elsetNameMap[elset.Name] = newName;
            // Replace elset name in keyword line
            var newKeywordLine = elset.KeywordLine.Replace($"elset={elset.Name}", $"elset={newName}");
            await writer.WriteLineAsync(newKeywordLine);
            foreach (var dataLine in elset.DataLines)
                await writer.WriteLineAsync(dataLine);
        }

        // === Surfaces from file1 ===
        var surfaceNameCounts = new Dictionary<string, int>();
        foreach (var surf in model1.AssemblySurfaces)
        {
            surfaceNameCounts[surf.Name] = 1;
            await writer.WriteLineAsync($"*Surface, type={surf.Type}, name={surf.Name}");
            foreach (var entry in surf.Entries)
                await writer.WriteLineAsync($"{entry.ElsetName}, {entry.FaceLabel}");
        }

        // === Surfaces from file2 (rename duplicates with suffix, update elset references) ===
        var surfaceNameMap = new Dictionary<string, string>(); // original -> renamed for model2
        foreach (var surf in model2.AssemblySurfaces)
        {
            string newName = surf.Name;
            if (surfaceNameCounts.ContainsKey(surf.Name))
            {
                surfaceNameCounts[surf.Name]++;
                newName = $"{surf.Name}_{surfaceNameCounts[surf.Name]}";
            }
            else
            {
                surfaceNameCounts[surf.Name] = 1;
            }
            surfaceNameMap[surf.Name] = newName;
            await writer.WriteLineAsync($"*Surface, type={surf.Type}, name={newName}");
            foreach (var entry in surf.Entries)
            {
                // Use renamed elset name if available
                string newElsetName = elsetNameMap.TryGetValue(entry.ElsetName, out var mapped) ? mapped : entry.ElsetName;
                await writer.WriteLineAsync($"{newElsetName}, {entry.FaceLabel}");
            }
        }

        // === Couplings from file1 ===
        var couplingNameCounts = new Dictionary<string, int>();
        foreach (var coupling in model1.AssemblyCouplings)
        {
            couplingNameCounts[coupling.Name] = 1;
            await writer.WriteLineAsync($"*Coupling, constraint name={coupling.Name}, ref node={coupling.RefNodeSet}, surface={coupling.Surface}");
            await writer.WriteLineAsync(coupling.ConstraintType);
        }

        // === Couplings from file2 (rename duplicates with suffix, update references) ===
        foreach (var coupling in model2.AssemblyCouplings)
        {
            string newName = coupling.Name;
            string newSurface = coupling.Surface;
            string newRefNode = coupling.RefNodeSet;
            
            if (couplingNameCounts.ContainsKey(coupling.Name))
            {
                couplingNameCounts[coupling.Name]++;
                newName = $"{coupling.Name}_{couplingNameCounts[coupling.Name]}";
            }
            else
            {
                couplingNameCounts[coupling.Name] = 1;
            }
            
            // Map surface to renamed version if available
            if (surfaceNameMap.TryGetValue(coupling.Surface, out var mappedSurface))
                newSurface = mappedSurface;
            
            // Map ref node to renamed version  
            if (nsetNameMap.TryGetValue(coupling.RefNodeSet, out var mappedNode))
                newRefNode = mappedNode;
            
            await writer.WriteLineAsync($"*Coupling, constraint name={newName}, ref node={newRefNode}, surface={newSurface}");
            await writer.WriteLineAsync(coupling.ConstraintType);
        }

        await writer.WriteLineAsync("*End Assembly");
        log($"已写入合并 Assembly，含 {instanceCount} 个实例、{surfaceNameCounts.Count} 个 Surface、{couplingNameCounts.Count} 个约束");
    }

    /// <summary>
    /// Writes ID values as comma-separated lines (up to 16 per line) asynchronously.
    /// </summary>
    private static async Task WriteIdsAsync(StreamWriter writer, int[] ids)
    {
        if (ids.Length == 0) return;

        const int maxPerLine = 16;
        for (int offset = 0; offset < ids.Length; offset += maxPerLine)
        {
            var count = Math.Min(maxPerLine, ids.Length - offset);
            var chunk = ids.Skip(offset).Take(count);
            var line = string.Join(", ", chunk);
            if (count == 1 && offset + count == ids.Length)
                line += ",";
            await writer.WriteLineAsync(line);
        }
    }
}
