namespace AbaqusToolkit.Core.Models;

/// <summary>
/// Represents a coupling constraint (*Coupling) within the Assembly section.
/// </summary>
public class InpCoupling
{
    /// <summary>
    /// Constraint name (from *Coupling, constraint name=...).
    /// </summary>
    public string Name { get; set; } = string.Empty;

    /// <summary>
    /// Reference node set name (from *Coupling, ref node=...).
    /// </summary>
    public string RefNodeSet { get; set; } = string.Empty;

    /// <summary>
    /// Surface name (from *Coupling, surface=...).
    /// </summary>
    public string Surface { get; set; } = string.Empty;

    /// <summary>
    /// Constraint type keyword that follows the *Coupling line,
    /// e.g. "*Kinematic", "*Distributing".
    /// </summary>
    public string ConstraintType { get; set; } = string.Empty;
}
