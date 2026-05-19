namespace AbaqusToolkit.Core.Models;

/// <summary>
/// Represents a surface definition (*Surface) within the Assembly section.
/// A surface consists of one or more face entries, each referencing an element
/// set and a face identifier (e.g. S1, S2).
/// </summary>
public class InpSurface
{
    /// <summary>
    /// Surface name (from *Surface, name=...).
    /// </summary>
    public string Name { get; set; } = string.Empty;

    /// <summary>
    /// Surface type (from *Surface, type=...), e.g. "ELEMENT".
    /// </summary>
    public string Type { get; set; } = string.Empty;

    /// <summary>
    /// Face entries: each entry is (ElsetName, FaceLabel).
    /// </summary>
    public List<InpSurfaceEntry> Entries { get; set; } = new();
}

/// <summary>
/// A single face entry within a surface definition, e.g. "_s_Surf-1_S1, S1".
/// </summary>
public class InpSurfaceEntry
{
    /// <summary>
    /// Referenced element set name.
    /// </summary>
    public string ElsetName { get; set; } = string.Empty;

    /// <summary>
    /// Face label (e.g. "S1", "S2").
    /// </summary>
    public string FaceLabel { get; set; } = string.Empty;
}
