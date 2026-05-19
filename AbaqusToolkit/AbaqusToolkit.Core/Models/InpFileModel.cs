namespace AbaqusToolkit.Core.Models;

/// <summary>
/// Top-level model representing a complete parsed INP file.
/// Contains both raw passthrough lines and structured data for sections
/// that need programmatic manipulation.
/// </summary>
public class InpFileModel
{
    /// <summary>
    /// Lines before the first *Part keyword (typically *Heading and comments).
    /// </summary>
    public List<string> HeadingLines { get; set; } = new();

    /// <summary>
    /// Parsed Part definitions. Each part contains nodes, elements, sets, and section data.
    /// </summary>
    public List<InpPart> Parts { get; set; } = new();

    /// <summary>
    /// Raw lines of the Assembly section (*Assembly to *End Assembly inclusive).
    /// Used for passthrough when writing.
    /// </summary>
    public List<string> AssemblyLines { get; set; } = new();

    /// <summary>
    /// Structured Assembly data parsed from the Assembly section.
    /// </summary>
    public string AssemblyName { get; set; } = string.Empty;

    /// <summary>
    /// Instances defined within the Assembly.
    /// </summary>
    public List<InpInstance> AssemblyInstances { get; set; } = new();

    /// <summary>
    /// Reference nodes defined within the Assembly (*Node block).
    /// </summary>
    public List<InpNode> AssemblyRefNodes { get; set; } = new();

    /// <summary>
    /// Node sets (Nset) defined within the Assembly.
    /// </summary>
    public List<InpSet> AssemblyNsets { get; set; } = new();

    /// <summary>
    /// Element sets (Elset) defined within the Assembly, which may include
    /// instance= parameters pointing to specific instances.
    /// </summary>
    public List<InpAssemblyElset> AssemblyElsets { get; set; } = new();

    /// <summary>
    /// Surfaces defined within the Assembly.
    /// </summary>
    public List<InpSurface> AssemblySurfaces { get; set; } = new();

    /// <summary>
    /// Coupling constraints defined within the Assembly.
    /// </summary>
    public List<InpCoupling> AssemblyCouplings { get; set; } = new();

    /// <summary>
    /// Raw lines after *End Assembly to end of file (Material, Step, etc.).
    /// Used for passthrough when writing.
    /// </summary>
    public List<string> MaterialStepLines { get; set; } = new();
}
