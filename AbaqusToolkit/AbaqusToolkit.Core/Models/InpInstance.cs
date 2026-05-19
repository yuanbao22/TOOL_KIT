namespace AbaqusToolkit.Core.Models;

/// <summary>
/// Represents an Instance definition within the Assembly section.
/// </summary>
public class InpInstance
{
    /// <summary>
    /// Instance name (from *Instance, name=...).
    /// </summary>
    public string Name { get; set; } = string.Empty;

    /// <summary>
    /// Referenced part name (from *Instance, part=...).
    /// </summary>
    public string PartName { get; set; } = string.Empty;

    /// <summary>
    /// X translation offset for the instance placement.
    /// </summary>
    public double OffsetX { get; set; }

    /// <summary>
    /// Y translation offset for the instance placement.
    /// </summary>
    public double OffsetY { get; set; }

    /// <summary>
    /// Z translation offset for the instance placement.
    /// </summary>
    public double OffsetZ { get; set; }

    /// <summary>
    /// Whether this instance has an explicit offset (data line with coordinates).
    /// </summary>
    public bool HasOffset { get; set; }
}
