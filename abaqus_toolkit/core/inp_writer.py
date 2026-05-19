"""
Writes structured INP model data back to INP file format.
Supports Part renumbering with node and element offsets.

Maps 1:1 from the C# AbaqusToolkit.Core.Parsing.InpWriter static class.
"""

from .models import InpPart


def format_double(value: float) -> str:
    """
    Formats a double value without trailing zeros.

    Uses Python's general format specifier ('G') for clean representation,
    equivalent to C#'s value.ToString("G", CultureInfo.InvariantCulture).
    """
    return f"{value:G}"


def format_node_line(id: int, x: float, y: float, z: float) -> str:
    """
    Formats a single node line in Abaqus INP format.

    Format: "id, x, y, z" with clean float formatting.
    """
    return f"{id}, {format_double(x)}, {format_double(y)}, {format_double(z)}"


def format_element_line(id: int, node_ids: list[int]) -> str:
    """
    Formats a single element line in Abaqus INP format.

    Format: "id, n1, n2, n3, ..." comma-separated.
    """
    parts = [str(id)] + [str(n) for n in node_ids]
    return ", ".join(parts)


def write_id_lines(ids: list[int]) -> list[str]:
    """
    Writes ID values as comma-separated lines, respecting the Abaqus convention
    of up to 16 values per line.

    If a set contains exactly one value, the line ends with a trailing comma
    (INP convention for single-entry sets: "5,").
    """
    if not ids:
        return []

    max_per_line = 16
    lines: list[str] = []

    for offset in range(0, len(ids), max_per_line):
        chunk = ids[offset : offset + max_per_line]
        line = ", ".join(str(id) for id in chunk)

        # Single value on the last line → trailing comma per INP convention
        if len(chunk) == 1 and offset + len(chunk) == len(ids):
            line += ","

        lines.append(line)

    return lines


def write_part(part: InpPart, node_offset: int = 0, elem_offset: int = 0) -> list[str]:
    """
    Writes a single Part section to INP format lines, with optional ID offsets
    for renumbering nodes and elements (used when merging multiple files).

    Args:
        part: The part to write.
        node_offset: Offset added to all node IDs and node references.
        elem_offset: Offset added to all element IDs.

    Returns:
        List of lines representing the Part section.
    """
    lines: list[str] = []

    # *Part header
    lines.append(f"*Part, name={part.name}")

    # *Node block
    if part.nodes:
        lines.append("*Node")
        for node in part.nodes:
            new_id = node.id + node_offset
            lines.append(format_node_line(new_id, node.x, node.y, node.z))

    # *Element block
    if part.elements:
        type_suffix = f", type={part.element_type}" if part.element_type else ""
        lines.append(f"*Element{type_suffix}")

        for elem in part.elements:
            new_id = elem.id + elem_offset
            new_node_ids = [nid + node_offset for nid in elem.node_ids]
            lines.append(format_element_line(new_id, new_node_ids))

    # *Nset blocks
    for nset in part.nsets:
        if nset.is_generate:
            new_start = nset.start + node_offset
            new_end = nset.end + node_offset
            lines.append(f"*Nset, nset={nset.name}, generate")
            lines.append(f"{new_start}, {new_end}, {nset.step}")
        else:
            lines.append(f"*Nset, nset={nset.name}")
            offset_ids = [id + node_offset for id in nset.ids]
            lines.extend(write_id_lines(offset_ids))

    # *Elset blocks
    for elset in part.elsets:
        if elset.is_generate:
            new_start = elset.start + elem_offset
            new_end = elset.end + elem_offset
            lines.append(f"*Elset, elset={elset.name}, generate")
            lines.append(f"{new_start}, {new_end}, {elset.step}")
        else:
            lines.append(f"*Elset, elset={elset.name}")
            offset_ids = [id + elem_offset for id in elset.ids]
            lines.extend(write_id_lines(offset_ids))

    # Solid Section lines (written as-is; references are by name not ID)
    if part.solid_section_lines:
        lines.extend(part.solid_section_lines)

    # *End Part
    lines.append("*End Part")

    return lines
