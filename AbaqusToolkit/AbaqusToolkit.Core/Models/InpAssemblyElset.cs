namespace AbaqusToolkit.Core.Models;

/// <summary>
/// Represents an element set (Elset) within the Assembly section,
/// which may include an instance= parameter referencing a specific Instance.
/// </summary>
public class InpAssemblyElset
{
    /// <summary>
    /// Elset name.
    /// </summary>
    public string Name { get; set; } = string.Empty;

    /// <summary>
    /// Instance name if defined with instance= parameter.
    /// </summary>
    public string? InstanceName { get; set; }

    /// <summary>
    /// Whether this set uses the "generate" keyword.
    /// </summary>
    public bool IsGenerate { get; set; }

    /// <summary>
    /// Whether this set is marked as "internal".
    /// </summary>
    public bool IsInternal { get; set; }

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

    /// <summary>
    /// Raw keyword line for faithful reproduction.
    /// </summary>
    public string KeywordLine { get; set; } = string.Empty;

    /// <summary>
    /// Raw data lines for faithful reproduction.
    /// </summary>
    public List<string> DataLines { get; set; } = new();
}
