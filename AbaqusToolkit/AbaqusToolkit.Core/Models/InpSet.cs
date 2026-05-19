namespace AbaqusToolkit.Core.Models;

/// <summary>
/// Represents a node set (Nset) or element set (Elset) in an INP file.
/// Supports both generate mode (start, end, step) and explicit ID lists.
/// </summary>
public class InpSet
{
    /// <summary>
    /// The set name (e.g. "Set-1", "m_Set-1").
    /// </summary>
    public string Name { get; set; } = string.Empty;

    /// <summary>
    /// Whether this set uses the "generate" keyword for sequential ID ranges.
    /// </summary>
    public bool IsGenerate { get; set; }

    /// <summary>
    /// Start ID for generate mode.
    /// </summary>
    public int Start { get; set; }

    /// <summary>
    /// End ID (inclusive) for generate mode.
    /// </summary>
    public int End { get; set; }

    /// <summary>
    /// Step increment for generate mode.
    /// </summary>
    public int Step { get; set; }

    /// <summary>
    /// Explicit ID list for non-generate mode.
    /// </summary>
    public List<int> Ids { get; set; } = new();
}
