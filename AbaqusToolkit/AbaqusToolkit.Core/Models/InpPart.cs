namespace AbaqusToolkit.Core.Models;

/// <summary>
/// Represents a Part defined between *Part and *End Part in an INP file.
/// </summary>
public class InpPart
{
    /// <summary>
    /// Part name (from *Part, name=...).
    /// </summary>
    public string Name { get; set; } = string.Empty;

    /// <summary>
    /// Element type for this part (from *Element, type=...).
    /// </summary>
    public string ElementType { get; set; } = string.Empty;

    /// <summary>
    /// Nodes defined in this part.
    /// </summary>
    public List<InpNode> Nodes { get; set; } = new();

    /// <summary>
    /// Elements defined in this part.
    /// </summary>
    public List<InpElement> Elements { get; set; } = new();

    /// <summary>
    /// Node sets (Nset) defined in this part.
    /// </summary>
    public List<InpSet> Nsets { get; set; } = new();

    /// <summary>
    /// Element sets (Elset) defined in this part.
    /// </summary>
    public List<InpSet> Elsets { get; set; } = new();

    /// <summary>
    /// Raw lines for Solid Section definition, including the keyword line
    /// and data lines. These are written as-is during serialization since
    /// section definitions reference named sets (not numeric IDs).
    /// </summary>
    public List<string> SolidSectionLines { get; set; } = new();
}
