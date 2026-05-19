using AbaqusToolkit.Core.Parsing;
using AbaqusToolkit.Core.Models;
using Xunit;

namespace AbaqusToolkit.Tests.Parsing;

public class InpParserTests
{
    private static readonly string TestDir = @"D:\sy\temp000";
    private static string[] _job1Lines, _job2Lines;
    private static InpFileModel _job1Model, _job2Model;

    static InpParserTests()
    {
        _job1Lines = File.ReadAllLines(Path.Combine(TestDir, "Job-1.inp"));
        _job2Lines = File.ReadAllLines(Path.Combine(TestDir, "Job-2.inp"));
        _job1Model = InpParser.Parse(_job1Lines);
        _job2Model = InpParser.Parse(_job2Lines);
    }

    // ==================== Job-1 Tests ====================

    [Fact]
    public void Parse_Job1_HasHeading()
    {
        Assert.NotEmpty(_job1Model.HeadingLines);
        Assert.Contains("*Heading", _job1Model.HeadingLines[0]);
    }

    [Fact]
    public void Parse_Job1_OnePart()
    {
        Assert.Single(_job1Model.Parts);
    }

    [Fact]
    public void Parse_Job1_PartName()
    {
        var part = _job1Model.Parts[0];
        Assert.Equal("Part-1", part.Name);
    }

    [Fact]
    public void Parse_Job1_NodeCount()
    {
        var part = _job1Model.Parts[0];
        Assert.Equal(891, part.Nodes.Count);
    }

    [Fact]
    public void Parse_Job1_FirstNode()
    {
        var n = _job1Model.Parts[0].Nodes[0];
        Assert.Equal(1, n.Id);
        Assert.Equal(-40.0, n.X);
        Assert.Equal(-2.5, n.Y);
        Assert.Equal(20.0, n.Z);
    }

    [Fact]
    public void Parse_Job1_LastNode()
    {
        var n = _job1Model.Parts[0].Nodes[^1];
        Assert.Equal(891, n.Id);
    }


    [Fact]
    public void Parse_Job1_ElementType()
    {
        Assert.Equal("C3D8R", _job1Model.Parts[0].ElementType);
    }

    [Fact]
    public void Parse_Job1_ElementNodeCount()
    {
        var e = _job1Model.Parts[0].Elements[0];
        Assert.Equal(8, e.NodeIds.Length);
    }

    [Fact]
    public void Parse_Job1_NsetPresent()
    {
        var nset = _job1Model.Parts[0].Nsets.FirstOrDefault(s => s.Name == "Set-1");
        Assert.NotNull(nset);
        Assert.True(nset.IsGenerate);
    }

    [Fact]
    public void Parse_Job1_NsetRange()
    {
        var nset = _job1Model.Parts[0].Nsets.First(s => s.Name == "Set-1");
        Assert.Equal(1, nset.Start);
        Assert.Equal(891, nset.End);
        Assert.Equal(1, nset.Step);
    }

    [Fact]
    public void Parse_Job1_ElsetRange()
    {
        var elset = _job1Model.Parts[0].Elsets.First(s => s.Name == "Set-1");
        Assert.True(elset.IsGenerate);
        Assert.Equal(1, elset.Start);
        Assert.Equal(640, elset.End);
        Assert.Equal(1, elset.Step);
    }

    [Fact]
    public void Parse_Job1_HasAssembly()
    {
        Assert.NotEmpty(_job1Model.AssemblyLines);
        Assert.Contains("*Assembly", _job1Model.AssemblyLines[0]);
        Assert.NotEmpty(_job1Model.AssemblyInstances);
    }

    [Fact]
    public void Parse_Job1_AssemblyInstanceCount()
    {
        Assert.Equal(2, _job1Model.AssemblyInstances.Count);
    }

    [Fact]
    public void Parse_Job1_AssemblyRefNodeCount()
    {
        Assert.Single(_job1Model.AssemblyRefNodes);
    }

    [Fact]
    public void Parse_Job1_HasCoupling()
    {
        Assert.NotEmpty(_job1Model.AssemblyCouplings);
    }

    [Fact]
    public void Parse_Job1_HasMaterialStep()
    {
        Assert.NotEmpty(_job1Model.MaterialStepLines);
        Assert.Contains(_job1Model.MaterialStepLines,
            l => l.StartsWith("*Step"));
    }

    // ==================== Job-2 Tests ====================

    [Fact]
    public void Parse_Job2_PartName()
    {
        var part = _job2Model.Parts[0];
        Assert.Equal("Part-2", part.Name);
    }

    [Fact]
    public void Parse_Job2_SameStructureAsJob1()
    {
        Assert.Equal(_job1Model.Parts[0].Nodes.Count,
                     _job2Model.Parts[0].Nodes.Count);
        Assert.Equal(_job1Model.Parts[0].Elements.Count,
                     _job2Model.Parts[0].Elements.Count);
    }

    // ==================== InpWriter Tests ====================

    [Fact]
    public void WritePart_NoOffset_ProducesConsistentOutput()
    {
        var part = _job1Model.Parts[0];
        var lines = InpWriter.WritePart(part, 0, 0);

        Assert.Contains("*Part, name=Part-1", lines[0]);
        Assert.Contains("*Node", lines);
        Assert.Contains("*Element, type=C3D8R", lines);
        Assert.Contains("*End Part", lines[^1]);
    }

    [Fact]
    public void WritePart_WithNodeOffset_RenumbersNodes()
    {
        var part = _job1Model.Parts[0];
        var lines = InpWriter.WritePart(part, nodeOffset: 1000, elemOffset: 0);

        // Find a node data line - it should have id >= 1001
        var nodeLine = lines.FirstOrDefault(l =>
            l.Contains(",") && int.TryParse(l.Split(',')[0].Trim(), out var id) && id > 1000);
        Assert.NotNull(nodeLine);
    }

    [Fact]
    public void WritePart_WithElemOffset_RenumbersElements()
    {
        var part = _job1Model.Parts[0];
        int nodeOff = 1000, elemOff = 500;
        var lines = InpWriter.WritePart(part, nodeOff, elemOff);

        // Find C3D8R element line (9 numbers: 1 ID + 8 nodes)
        var elemLine = lines.FirstOrDefault(l =>
        {
            var p = l.Split(',');
            return p.Length == 9
                && int.TryParse(p[0].Trim(), out var id)
                && id > 500;
        });
        Assert.NotNull(elemLine);

        var parts = elemLine!.Split(',');
        var elemId = int.Parse(parts[0].Trim());
        Assert.True(elemId > 500);

        // First node reference should be renumbered
        var firstNode = int.Parse(parts[1].Trim());
        Assert.True(firstNode > 1000);
    }

    [Fact]
    public void WritePart_NsetGenerate_Renumbered()
    {
        var part = _job1Model.Parts[0];
        int nodeOff = 891;
        var lines = InpWriter.WritePart(part, nodeOff, 0);

        var nsetLine = lines.FirstOrDefault(l => l.StartsWith("*Nset, nset=Set-1"));
        Assert.NotNull(nsetLine);

        // Range line should have renumbered values
        var rangeIdx = Array.IndexOf(lines, nsetLine) + 1;
        var rangeLine = lines[rangeIdx].Split(',');
        Assert.Equal(892, int.Parse(rangeLine[0].Trim()));
        Assert.Equal(1782, int.Parse(rangeLine[1].Trim()));
    }

    [Fact]
    public void WritePart_ElsetGenerate_Renumbered()
    {
        var part = _job1Model.Parts[0];
        int elemOff = 640;
        var lines = InpWriter.WritePart(part, 0, elemOff);

        var elsetIdx = Array.FindIndex(lines, l => l.StartsWith("*Elset, elset=Set-1"));
        Assert.True(elsetIdx >= 0);

        var rangeLine = lines[elsetIdx + 1].Split(',');
        Assert.Equal(641, int.Parse(rangeLine[0].Trim()));
        Assert.Equal(1280, int.Parse(rangeLine[1].Trim()));
    }

    // ==================== Full Merge Tests ====================

    [Fact]
    public void Parse_FullMerge_file1OffsetDetection()
    {
        // Verify offsets that InpMergeService would compute
        int maxNode = _job1Model.Parts.Max(p => p.Nodes.Count > 0 ? p.Nodes.Max(n => n.Id) : 0);
        int maxElem = _job1Model.Parts.Max(p => p.Elements.Count > 0 ? p.Elements.Max(e => e.Id) : 0);

        Assert.Equal(891, maxNode);
        Assert.Equal(640, maxElem);
    }

    [Fact]
    public void Parse_File2PartCount()
    {
        Assert.Single(_job2Model.Parts);
        Assert.Equal(891, _job2Model.Parts[0].Nodes.Count);
    }
}
