namespace AbaqusToolkit;

public class MergeResult
{
    public bool Success { get; set; }
    public string OutputPath { get; set; } = string.Empty;
    public string Message { get; set; } = string.Empty;
    public List<string> LogLines { get; set; } = new();
    public int NodeOffset { get; set; }
    public int ElemOffset { get; set; }
}
