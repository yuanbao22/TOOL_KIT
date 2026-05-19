using System.Globalization;
using AbaqusToolkit.Core.Models;

namespace AbaqusToolkit.Core.Parsing;

/// <summary>
/// Writes structured INP model data back to INP file format.
/// Supports Part renumbering with node and element offsets.
/// </summary>
public static class InpWriter
{
    /// <summary>
    /// Writes a single Part section to INP format lines, with optional ID offsets
    /// for renumbering nodes and elements (used when merging multiple files).
    /// </summary>
    /// <param name="part">The part to write.</param>
    /// <param name="nodeOffset">Offset added to all node IDs and node references.</param>
    /// <param name="elemOffset">Offset added to all element IDs.</param>
    /// <returns>Array of lines representing the Part section.</returns>
    public static string[] WritePart(InpPart part, int nodeOffset = 0, int elemOffset = 0)
    {
        var lines = new List<string>();

        // *Part header
        lines.Add($"*Part, name={part.Name}");

        // *Node block
        if (part.Nodes.Count > 0)
        {
            lines.Add("*Node");
            foreach (var node in part.Nodes)
            {
                var newId = node.Id + nodeOffset;
                lines.Add(FormatNodeLine(newId, node.X, node.Y, node.Z));
            }
        }

        // *Element block
        if (part.Elements.Count > 0)
        {
            var typeSuffix = string.IsNullOrEmpty(part.ElementType) ? "" : $", type={part.ElementType}";
            lines.Add($"*Element{typeSuffix}");

            foreach (var elem in part.Elements)
            {
                var newId = elem.Id + elemOffset;
                var newNodeIds = new int[elem.NodeIds.Length];
                for (int j = 0; j < elem.NodeIds.Length; j++)
                    newNodeIds[j] = elem.NodeIds[j] + nodeOffset;

                lines.Add(FormatElementLine(newId, newNodeIds));
            }
        }

        // *Nset blocks
        foreach (var nset in part.Nsets)
        {
            if (nset.IsGenerate)
            {
                var newStart = nset.Start + nodeOffset;
                var newEnd = nset.End + nodeOffset;
                lines.Add($"*Nset, nset={nset.Name}, generate");
                lines.Add($"{newStart}, {newEnd}, {nset.Step}");
            }
            else
            {
                lines.Add($"*Nset, nset={nset.Name}");
                var offsetIds = nset.Ids.Select(id => id + nodeOffset).ToArray();
                WriteIdLines(lines, offsetIds);
            }
        }

        // *Elset blocks
        foreach (var elset in part.Elsets)
        {
            if (elset.IsGenerate)
            {
                var newStart = elset.Start + elemOffset;
                var newEnd = elset.End + elemOffset;
                lines.Add($"*Elset, elset={elset.Name}, generate");
                lines.Add($"{newStart}, {newEnd}, {elset.Step}");
            }
            else
            {
                lines.Add($"*Elset, elset={elset.Name}");
                var offsetIds = elset.Ids.Select(id => id + elemOffset).ToArray();
                WriteIdLines(lines, offsetIds);
            }
        }

        // Solid Section lines (written as-is; references are by name not ID)
        if (part.SolidSectionLines.Count > 0)
        {
            foreach (var line in part.SolidSectionLines)
                lines.Add(line);
        }

        // *End Part
        lines.Add("*End Part");

        return lines.ToArray();
    }

    #region Formatting helpers

    private static string FormatNodeLine(int id, double x, double y, double z)
    {
        return string.Format(CultureInfo.InvariantCulture,
            "{0}, {1}, {2}, {3}",
            id, FormatDouble(x), FormatDouble(y), FormatDouble(z));
    }

    private static string FormatElementLine(int id, int[] nodeIds)
    {
        var parts = new string[1 + nodeIds.Length];
        parts[0] = id.ToString(CultureInfo.InvariantCulture);
        for (int i = 0; i < nodeIds.Length; i++)
            parts[i + 1] = nodeIds[i].ToString(CultureInfo.InvariantCulture);
        return string.Join(", ", parts);
    }

    /// <summary>
    /// Writes ID values as comma-separated lines, respecting the Abaqus convention
    /// of up to 16 values per line. Each non-final line ends with a comma to indicate
    /// continuation.
    /// </summary>
    private static void WriteIdLines(List<string> lines, int[] ids)
    {
        if (ids.Length == 0) return;

        const int maxPerLine = 16;
        for (int offset = 0; offset < ids.Length; offset += maxPerLine)
        {
            var count = Math.Min(maxPerLine, ids.Length - offset);
            var chunk = ids.Skip(offset).Take(count);
            var line = string.Join(", ", chunk);
            // Per INP convention, if a set entry is a single value, it still ends with comma
            if (count == 1 && offset + count == ids.Length)
                line += ",";
            lines.Add(line);
        }
    }

    /// <summary>
    /// Formats a double value without trailing zeros, using invariant culture.
    /// </summary>
    private static string FormatDouble(double value)
    {
        // Use "G" format to avoid excessive precision while keeping clean representation
        return value.ToString("G", CultureInfo.InvariantCulture);
    }

    #endregion
}
