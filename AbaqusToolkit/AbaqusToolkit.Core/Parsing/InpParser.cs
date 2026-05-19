using System.Globalization;
using AbaqusToolkit.Core.Models;

namespace AbaqusToolkit.Core.Parsing;

/// <summary>
/// Parses Abaqus INP files into a structured <see cref="InpFileModel"/>.
/// Supports Part, Assembly, Material, and Step sections.
/// </summary>
public static class InpParser
{
    /// <summary>
    /// Parses an array of INP file lines into a fully structured model.
    /// </summary>
    /// <param name="lines">Lines of the INP file.</param>
    /// <returns>A populated <see cref="InpFileModel"/>.</returns>
    public static InpFileModel Parse(string[] lines)
    {
        var model = new InpFileModel();
        int i = 0;

        // Phase 1: Heading — everything before the first *Part
        i = ParseHeading(lines, i, model);

        // Phase 2: Parts — between *Part and *End Part, may be multiple
        i = ParseParts(lines, i, model);

        // Phase 3: Assembly — between *Assembly and *End Assembly
        i = ParseAssembly(lines, i, model);

        // Phase 4: Material/Step — everything after *End Assembly
        i = ParseMaterialStep(lines, i, model);

        return model;
    }

    #region Phase 1: Heading

    private static int ParseHeading(string[] lines, int i, InpFileModel model)
    {
        while (i < lines.Length && !IsKeyword(lines[i], "Part"))
        {
            model.HeadingLines.Add(lines[i]);
            i++;
        }
        return i;
    }

    #endregion

    #region Phase 2: Parts

    private static int ParseParts(string[] lines, int i, InpFileModel model)
    {
        while (i < lines.Length && !IsKeyword(lines[i], "Assembly"))
        {
            if (IsKeyword(lines[i], "Part"))
            {
                var part = ParseOnePart(lines, ref i);
                if (part != null)
                    model.Parts.Add(part);
            }
            else
            {
                i++;
            }
        }
        return i;
    }

    private static InpPart? ParseOnePart(string[] lines, ref int i)
    {
        var part = new InpPart();

        // Parse *Part, name=XXX
        var partParams = ParseParameters(lines[i]);
        part.Name = partParams.TryGetValue("name", out var n) ? n : string.Empty;
        i++;

        List<string> pendingCommentLines = new();

        while (i < lines.Length && !IsKeyword(lines[i], "End Part"))
        {
            var line = lines[i];
            var trimmed = line.TrimStart();

            // Check if this is actually inside a nested *Part (unusual but defensive)
            if (IsKeyword(line, "Part"))
                break;

            // Collect comment lines that may annotate the next keyword block
            if (IsComment(trimmed))
            {
                pendingCommentLines.Add(line);
                i++;
                continue;
            }

            // Skip empty lines
            if (string.IsNullOrWhiteSpace(trimmed))
            {
                i++;
                continue;
            }

            // Not a keyword line? It's likely a continuation or stray data line — skip
            if (!trimmed.StartsWith('*'))
            {
                i++;
                continue;
            }

            if (IsKeyword(line, "Node"))
            {
                ParseNodes(lines, ref i, part.Nodes);
                pendingCommentLines.Clear();
            }
            else if (IsKeyword(line, "Element"))
            {
                var elemParams = ParseParameters(line);
                part.ElementType = elemParams.TryGetValue("type", out var et) ? et : string.Empty;
                ParseElements(lines, ref i, part.Elements);
                pendingCommentLines.Clear();
            }
            else if (IsKeyword(line, "Nset"))
            {
                var set = ParseSet(lines, ref i, "nset");
                if (set != null) part.Nsets.Add(set);
                pendingCommentLines.Clear();
            }
            else if (IsKeyword(line, "Elset"))
            {
                var set = ParseSet(lines, ref i, "elset");
                if (set != null) part.Elsets.Add(set);
                pendingCommentLines.Clear();
            }
            else if (IsKeyword(line, "Solid Section"))
            {
                // Include preceding comment lines as annotation
                foreach (var cl in pendingCommentLines)
                    part.SolidSectionLines.Add(cl);
                pendingCommentLines.Clear();

                part.SolidSectionLines.Add(line);
                i++;
                // Read data lines until next keyword or end of part
                while (i < lines.Length
                       && !lines[i].TrimStart().StartsWith('*')
                       && !IsKeyword(lines[i], "End Part"))
                {
                    if (!string.IsNullOrWhiteSpace(lines[i]))
                        part.SolidSectionLines.Add(lines[i]);
                    i++;
                }
            }
            else
            {
                // Unknown keyword within part — skip
                pendingCommentLines.Clear();
                i++;
            }
        }

        // Skip *End Part
        if (i < lines.Length)
            i++;

        return part;
    }

    #endregion

    #region Phase 3: Assembly

    private static int ParseAssembly(string[] lines, int i, InpFileModel model)
    {
        if (i >= lines.Length || !IsKeyword(lines[i], "Assembly"))
            return i;

        var asmParams = ParseParameters(lines[i]);
        model.AssemblyName = asmParams.TryGetValue("name", out var an) ? an : string.Empty;

        // Collect raw lines for passthrough, starting with *Assembly
        int assemblyStart = i;
        i++; // skip *Assembly

        while (i < lines.Length && !IsKeyword(lines[i], "End Assembly"))
        {
            var line = lines[i];
            var trimmed = line.TrimStart();

            if (IsComment(trimmed) || string.IsNullOrWhiteSpace(trimmed))
            {
                i++;
                continue;
            }

            if (!trimmed.StartsWith('*'))
            {
                // Data line — handled within each sub-parser, but standalone data lines
                // (e.g. Instance offset coordinates already consumed) are skipped here.
                i++;
                continue;
            }

            if (IsKeyword(line, "Instance"))
            {
                var inst = ParseInstance(lines, ref i);
                if (inst != null) model.AssemblyInstances.Add(inst);
            }
            else if (IsKeyword(line, "Node"))
            {
                ParseNodes(lines, ref i, model.AssemblyRefNodes);
            }
            else if (IsKeyword(line, "Nset"))
            {
                var set = ParseSet(lines, ref i, "nset");
                if (set != null) model.AssemblyNsets.Add(set);
            }
            else if (IsKeyword(line, "Elset"))
            {
                var elset = ParseAssemblyElset(lines, ref i);
                if (elset != null) model.AssemblyElsets.Add(elset);
            }
            else if (IsKeyword(line, "Surface"))
            {
                var surf = ParseSurface(lines, ref i);
                if (surf != null) model.AssemblySurfaces.Add(surf);
            }
            else if (IsKeyword(line, "Coupling"))
            {
                var coupling = ParseCoupling(lines, ref i);
                if (coupling != null) model.AssemblyCouplings.Add(coupling);
            }
            else
            {
                i++;
            }
        }

        // Collect raw Assembly lines for passthrough
        for (int j = assemblyStart; j <= i && j < lines.Length; j++)
        {
            model.AssemblyLines.Add(lines[j]);
        }

        // Skip *End Assembly
        if (i < lines.Length)
            i++;

        return i;
    }

    #endregion

    #region Phase 4: Material/Step

    private static int ParseMaterialStep(string[] lines, int i, InpFileModel model)
    {
        while (i < lines.Length)
        {
            model.MaterialStepLines.Add(lines[i]);
            i++;
        }
        return i;
    }

    #endregion

    #region Sub-parsers

    private static void ParseNodes(string[] lines, ref int i, List<InpNode> nodes)
    {
        i++;
        while (i < lines.Length)
        {
            var trimmed = lines[i].TrimStart();
            if (trimmed.StartsWith('*') || IsComment(trimmed))
                break;

            if (!string.IsNullOrWhiteSpace(lines[i]))
            {
                var node = ParseNodeDataLine(lines[i]);
                if (node != null) nodes.Add(node);
            }
            i++;
        }
    }

    private static InpNode? ParseNodeDataLine(string line)
    {
        var parts = line.Split(',');
        if (parts.Length < 4) return null;

        if (int.TryParse(parts[0].Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out int id)
            && double.TryParse(parts[1].Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out double x)
            && double.TryParse(parts[2].Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out double y)
            && double.TryParse(parts[3].Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out double z))
        {
            return new InpNode(id, x, y, z);
        }
        return null;
    }

    private static void ParseElements(string[] lines, ref int i, List<InpElement> elements)
    {
        i++;
        while (i < lines.Length)
        {
            var trimmed = lines[i].TrimStart();
            if (trimmed.StartsWith('*') || IsComment(trimmed))
                break;

            if (!string.IsNullOrWhiteSpace(lines[i]))
            {
                var elem = ParseElementDataLine(lines[i]);
                if (elem != null) elements.Add(elem);
            }
            i++;
        }
    }

    private static InpElement? ParseElementDataLine(string line)
    {
        var parts = line.Split(',');
        if (parts.Length < 2) return null;

        if (!int.TryParse(parts[0].Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out int id))
            return null;

        var nodeIds = new int[parts.Length - 1];
        bool allValid = true;
        for (int j = 1; j < parts.Length; j++)
        {
            if (!int.TryParse(parts[j].Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out nodeIds[j - 1]))
            {
                allValid = false;
                break;
            }
        }

        if (!allValid) return null;
        return new InpElement(id, nodeIds);
    }

    private static InpSet? ParseSet(string[] lines, ref int i, string nameParam)
    {
        var keywordLine = lines[i];
        var parameters = ParseParameters(keywordLine);
        var setName = parameters.TryGetValue(nameParam, out var sn) ? sn : string.Empty;
        bool isGenerate = parameters.ContainsKey("generate");

        var set = new InpSet
        {
            Name = setName,
            IsGenerate = isGenerate
        };

        i++;

        if (isGenerate)
        {
            // Read single data line: start, end, step
            while (i < lines.Length)
            {
                var trimmed = lines[i].TrimStart();
                if (trimmed.StartsWith('*') || IsComment(trimmed))
                    break;

                if (!string.IsNullOrWhiteSpace(lines[i]))
                {
                    var parts = lines[i].Split(',');
                    if (parts.Length >= 2)
                    {
                        int.TryParse(parts[0].Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out int start);
                        int.TryParse(parts[1].Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out int end);
                        int step = 1;
                        if (parts.Length >= 3)
                            int.TryParse(parts[2].Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out step);

                        set.Start = start;
                        set.End = end;
                        set.Step = step;
                    }
                    i++;
                    break;
                }
                i++;
            }
        }
        else
        {
            // Read data lines with IDs (up to 16 per line)
            while (i < lines.Length)
            {
                var trimmed = lines[i].TrimStart();
                if (trimmed.StartsWith('*') || IsComment(trimmed))
                    break;

                if (!string.IsNullOrWhiteSpace(lines[i]))
                {
                    var parts = lines[i].Split(',');
                    foreach (var p in parts)
                    {
                        var val = p.Trim();
                        if (int.TryParse(val, NumberStyles.Any, CultureInfo.InvariantCulture, out int id))
                            set.Ids.Add(id);
                    }
                }
                i++;
            }
        }

        return set;
    }

    private static InpAssemblyElset? ParseAssemblyElset(string[] lines, ref int i)
    {
        var keywordLine = lines[i];
        var parameters = ParseParameters(keywordLine);
        var elsetName = parameters.TryGetValue("elset", out var en) ? en : string.Empty;
        bool isGenerate = parameters.ContainsKey("generate");
        bool isInternal = parameters.ContainsKey("internal");
        string? instanceName = parameters.TryGetValue("instance", out var inst) ? inst : null;

        var elset = new InpAssemblyElset
        {
            Name = elsetName,
            IsGenerate = isGenerate,
            IsInternal = isInternal,
            InstanceName = instanceName,
            KeywordLine = keywordLine
        };

        i++;

        if (isGenerate)
        {
            while (i < lines.Length)
            {
                var trimmed = lines[i].TrimStart();
                if (trimmed.StartsWith('*') || IsComment(trimmed))
                    break;

                if (!string.IsNullOrWhiteSpace(lines[i]))
                {
                    elset.DataLines.Add(lines[i]);
                    var parts = lines[i].Split(',');
                    if (parts.Length >= 2)
                    {
                        int.TryParse(parts[0].Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out int start);
                        int.TryParse(parts[1].Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out int end);
                        int step = 1;
                        if (parts.Length >= 3)
                            int.TryParse(parts[2].Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out step);
                        elset.Start = start;
                        elset.End = end;
                        elset.Step = step;
                    }
                    i++;
                    break;
                }
                i++;
            }
        }
        else
        {
            while (i < lines.Length)
            {
                var trimmed = lines[i].TrimStart();
                if (trimmed.StartsWith('*') || IsComment(trimmed))
                    break;

                if (!string.IsNullOrWhiteSpace(lines[i]))
                {
                    elset.DataLines.Add(lines[i]);
                    var parts = lines[i].Split(',');
                    foreach (var p in parts)
                    {
                        var val = p.Trim();
                        if (int.TryParse(val, NumberStyles.Any, CultureInfo.InvariantCulture, out int id))
                            elset.Ids.Add(id);
                    }
                }
                i++;
            }
        }

        return elset;
    }

    private static InpInstance? ParseInstance(string[] lines, ref int i)
    {
        var parameters = ParseParameters(lines[i]);
        var name = parameters.TryGetValue("name", out var nm) ? nm : string.Empty;
        var partName = parameters.TryGetValue("part", out var pn) ? pn : string.Empty;

        var instance = new InpInstance
        {
            Name = name,
            PartName = partName
        };

        i++;

        // Check for offset data line (x, y, z) before *End Instance
        while (i < lines.Length)
        {
            var trimmed = lines[i].TrimStart();

            if (IsKeyword(lines[i], "End Instance"))
            {
                i++;
                break;
            }

            if (IsComment(trimmed) || string.IsNullOrWhiteSpace(trimmed))
            {
                i++;
                continue;
            }

            if (trimmed.StartsWith('*'))
            {
                // Unexpected keyword before *End Instance — stop
                break;
            }

            // Try to parse offset coordinates
            var parts = lines[i].Split(',');
            if (parts.Length >= 3)
            {
                if (double.TryParse(parts[0].Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out double ox)
                    && double.TryParse(parts[1].Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out double oy)
                    && double.TryParse(parts[2].Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out double oz))
                {
                    instance.OffsetX = ox;
                    instance.OffsetY = oy;
                    instance.OffsetZ = oz;
                    instance.HasOffset = true;
                    i++;
                    // Check for *End Instance on next line
                    if (i < lines.Length && IsKeyword(lines[i], "End Instance"))
                        i++;
                    break;
                }
            }
            i++;
            break;
        }

        return instance;
    }

    private static InpSurface? ParseSurface(string[] lines, ref int i)
    {
        var parameters = ParseParameters(lines[i]);
        var name = parameters.TryGetValue("name", out var sn) ? sn : string.Empty;
        var type = parameters.TryGetValue("type", out var st) ? st : string.Empty;

        var surface = new InpSurface
        {
            Name = name,
            Type = type
        };

        i++;

        // Read face entries until next keyword
        while (i < lines.Length)
        {
            var trimmed = lines[i].TrimStart();
            if (trimmed.StartsWith('*') || IsComment(trimmed))
                break;

            if (!string.IsNullOrWhiteSpace(lines[i]))
            {
                var parts = lines[i].Split(',');
                if (parts.Length >= 2)
                {
                    surface.Entries.Add(new InpSurfaceEntry
                    {
                        ElsetName = parts[0].Trim(),
                        FaceLabel = parts[1].Trim()
                    });
                }
            }
            i++;
        }

        return surface;
    }

    private static InpCoupling? ParseCoupling(string[] lines, ref int i)
    {
        var parameters = ParseParameters(lines[i]);
        var name = parameters.TryGetValue("constraint name", out var cn) ? cn : string.Empty;
        var refNode = parameters.TryGetValue("ref node", out var rn) ? rn : string.Empty;
        var surface = parameters.TryGetValue("surface", out var srf) ? srf : string.Empty;

        var coupling = new InpCoupling
        {
            Name = name,
            RefNodeSet = refNode,
            Surface = surface
        };

        i++;

        // Read constraint type keyword (e.g. *Kinematic) on next line
        while (i < lines.Length)
        {
            var trimmed = lines[i].TrimStart();

            if (IsComment(trimmed) || string.IsNullOrWhiteSpace(trimmed))
            {
                i++;
                continue;
            }

            if (trimmed.StartsWith('*'))
            {
                coupling.ConstraintType = trimmed;
                i++;
                break;
            }

            // Data line — skip
            i++;
        }

        return coupling;
    }

    #endregion

    #region Keyword and parameter helpers

    /// <summary>
    /// Checks whether a line starts with the specified INP keyword.
    /// Ensures exact keyword match (e.g. "Element" does not match "Elset").
    /// </summary>
    internal static bool IsKeyword(string line, string keyword)
    {
        if (string.IsNullOrEmpty(line)) return false;
        var trimmed = line.TrimStart();
        if (!trimmed.StartsWith('*')) return false;

        var rest = trimmed[1..]; // skip '*'

        // Handle multi-word keywords like "Solid Section", "End Part", "End Assembly"
        if (!rest.StartsWith(keyword, StringComparison.OrdinalIgnoreCase))
            return false;

        if (rest.Length == keyword.Length)
            return true;

        var nextChar = rest[keyword.Length];
        return nextChar == ',' || nextChar == ' ' || nextChar == '\t';
    }

    /// <summary>
    /// Parses comma-separated parameters from an INP keyword line.
    /// Handles key=value pairs and flag parameters (without =).
    /// Handles parameter names with spaces (e.g. "constraint name").
    /// </summary>
    internal static Dictionary<string, string> ParseParameters(string line)
    {
        var result = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        if (string.IsNullOrEmpty(line)) return result;

        // Remove the leading '*' and keyword
        var trimmed = line.TrimStart();
        var firstComma = trimmed.IndexOf(',');
        if (firstComma < 0) return result;

        var paramSection = trimmed[(firstComma + 1)..].Trim();
        if (string.IsNullOrEmpty(paramSection)) return result;

        var parts = paramSection.Split(',');
        foreach (var part in parts)
        {
            var p = part.Trim();
            if (string.IsNullOrEmpty(p)) continue;

            var eqIndex = p.IndexOf('=');
            if (eqIndex >= 0)
            {
                var key = p[..eqIndex].Trim();
                var value = p[(eqIndex + 1)..].Trim();
                if (!string.IsNullOrEmpty(key))
                    result[key] = value;
            }
            else
            {
                // Flag without value (e.g. "generate", "internal")
                result[p] = string.Empty;
            }
        }

        return result;
    }

    /// <summary>
    /// Checks if a trimmed line is an INP comment (starts with **).
    /// </summary>
    private static bool IsComment(string trimmedLine)
    {
        return trimmedLine.StartsWith("**");
    }

    #endregion
}
