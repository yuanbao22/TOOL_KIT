"""
INP file parser — translates Abaqus INP files into a structured InpFileModel.

Translates the C# InpParser.cs logic to Python with identical behavior.
All functions are standalone — no classes needed.
"""

from .models import (
    InpAssemblyElset,
    InpConstraint,
    InpCoupling,
    InpElement,
    InpFileModel,
    InpInstance,
    InpNode,
    InpOrientation,
    InpPart,
    InpSet,
    InpSurface,
    InpSurfaceEntry,
)


# ── Top-level parse entry point ──────────────────────────────────────────────


def parse(lines: list[str]) -> InpFileModel:
    """
    Parse an INP file (provided as a list of lines) into a structured model.

    Executes 4 phases:
      1. Heading — lines before the first *Part
      2. Parts   — *Part ... *End Part blocks
      3. Assembly — *Assembly ... *End Assembly block
      4. Material/Step — everything after *End Assembly

    :param lines: All lines of the INP file.
    :return: A fully populated InpFileModel.
    """
    model = InpFileModel()
    i = 0

    # Phase 1
    i = _parse_heading(lines, i, model)

    # Phase 2
    i = _parse_parts(lines, i, model)

    # Phase 3
    i = _parse_assembly(lines, i, model)

    # Phase 4
    i = _parse_material_step(lines, i, model)

    return model


# ── Phase 1: Heading ─────────────────────────────────────────────────────────


def _parse_heading(lines: list[str], i: int, model: InpFileModel) -> int:
    """Collect all lines before the first *Part or *Assembly keyword."""
    while i < len(lines) and not _is_keyword(lines[i], "Part") and not _is_keyword(lines[i], "Assembly"):
        model.heading_lines.append(lines[i])
        i += 1
    return i


# ── Phase 2: Parts ───────────────────────────────────────────────────────────


def _parse_parts(lines: list[str], i: int, model: InpFileModel) -> int:
    """Parse one or more ``*Part ... *End Part`` blocks."""
    while i < len(lines) and not _is_keyword(lines[i], "Assembly"):
        if _is_keyword(lines[i], "Part"):
            i, part = _parse_one_part(lines, i)
            if part is not None:
                model.parts.append(part)
        else:
            i += 1
    return i


def _parse_one_part(lines: list[str], i: int) -> tuple[int, "InpPart | None"]:
    """Parse a single ``*Part ... *End Part`` block. Returns (new_index, part)."""
    part = InpPart()

    # Parse *Part, name=XXX
    part_params = _parse_parameters(lines[i])
    part.name = part_params.get("name", "")
    i += 1

    pending_comment_lines: list[str] = []

    while i < len(lines) and not _is_keyword(lines[i], "End Part"):
        line = lines[i]
        trimmed = line.lstrip()

        # Guard against nested *Part (defensive)
        if _is_keyword(line, "Part"):
            break

        # Collect comment lines that may annotate the next keyword block
        if _is_comment(trimmed):
            pending_comment_lines.append(line)
            i += 1
            continue

        # Skip empty lines
        if not trimmed:
            i += 1
            continue

        # Not a keyword line — likely continuation or stray data, skip
        if not trimmed.startswith("*"):
            i += 1
            continue

        # ── Dispatch known keywords ──────────────────────────────────────────

        if _is_keyword(line, "Node"):
            i = _parse_nodes(lines, i, part.nodes)
            pending_comment_lines.clear()

        elif _is_keyword(line, "Element"):
            elem_params = _parse_parameters(line)
            # Guard: skip false *Element matches like *Element Output
            # which have no "type=" parameter and are step-level keywords.
            if "type" not in elem_params:
                i += 1
                continue
            block_type = elem_params["type"]
            # Record per-block type (preserve original type for each block)
            block_start = len(part.elements)
            part.element_type = block_type
            i = _parse_elements(lines, i, part.elements)
            block_elems = part.elements[block_start:]
            part.element_blocks.append((block_type, block_elems))
            pending_comment_lines.clear()

        elif _is_keyword(line, "Nset"):
            i, nset = _parse_set(lines, i, "nset")
            if nset is not None:
                part.nsets.append(nset)
            pending_comment_lines.clear()

        elif _is_keyword(line, "Elset"):
            i, elset = _parse_set(lines, i, "elset")
            if elset is not None:
                part.elsets.append(elset)
            pending_comment_lines.clear()

        elif _is_keyword(line, "Solid Section"):
            # Include preceding comment lines as annotation
            part.solid_section_lines.extend(pending_comment_lines)
            pending_comment_lines.clear()

            part.solid_section_lines.append(line)
            i += 1
            # Read data lines until next keyword or end of part
            while i < len(lines) and not lines[i].lstrip().startswith("*") and not _is_keyword(lines[i], "End Part"):
                if lines[i].strip():
                    part.solid_section_lines.append(lines[i])
                i += 1

        elif _is_keyword(line, "Shell Section"):
            # Include preceding comment lines as annotation
            part.shell_section_lines.extend(pending_comment_lines)
            pending_comment_lines.clear()

            part.shell_section_lines.append(line)
            i += 1
            # Read data lines until next keyword or end of part
            while i < len(lines) and not lines[i].lstrip().startswith("*") and not _is_keyword(lines[i], "End Part"):
                if lines[i].strip():
                    part.shell_section_lines.append(lines[i])
                i += 1

        elif _is_keyword(line, "Orientation"):
            pending_comment_lines.clear()
            orient_lines: list[str] = [line]
            i += 1
            # Read definition lines until next keyword or end of part
            while i < len(lines) and not lines[i].lstrip().startswith("*") and not _is_keyword(lines[i], "End Part"):
                if lines[i].strip():
                    orient_lines.append(lines[i])
                i += 1
            orient_name = _parse_parameters(line).get("name", "")
            if orient_name:
                part.orientations.append(InpOrientation(name=orient_name, lines=orient_lines))

        else:
            # Unknown keyword within part — preserve keyword + data lines
            # This catches *Beam Section, *Spring, *Spring Section, *Mass,
            # *Dashpot, *Rotary Inertia, and any other unhandled keyword.
            block_lines: list[str] = list(pending_comment_lines)
            pending_comment_lines.clear()
            block_lines.append(line)
            i += 1
            # Read data lines until next keyword or end of part
            while i < len(lines) and not lines[i].lstrip().startswith("*") and not _is_keyword(lines[i], "End Part"):
                if lines[i].strip():
                    block_lines.append(lines[i])
                i += 1
            part.unknown_block_lines.append(block_lines)

    # Skip *End Part
    if i < len(lines):
        i += 1

    return i, part


# ── Phase 3: Assembly ────────────────────────────────────────────────────────

# Constraint keywords recognised at the assembly level. Each defines a
# constraint that may carry a name= (or constraint name=) parameter and
# references surfaces, node sets, or element sets.
_CONSTRAINT_KEYWORDS = frozenset({
    "Tie", "Rigid Body", "Display Body", "Coupling",
    "Embedded Element", "Equation",
})


def _is_assembly_constraint(line: str) -> str:
    """Return the constraint type string if *line* is a recognised constraint
    keyword, or ``""`` otherwise."""
    trimmed = line.lstrip()
    if not trimmed.startswith("*"):
        return ""
    # Extract the keyword name (before any comma/space)
    rest = trimmed[1:].strip()
    kw = rest.split(",")[0].split(" ")[0].strip()
    # Also try 2-word forms like "Rigid Body", "Display Body", "Embedded Element"
    for two_word in ("Rigid Body", "Display Body", "Embedded Element"):
        if rest.lower().startswith(two_word.lower()):
            return two_word
    if kw in _CONSTRAINT_KEYWORDS:
        return kw
    return ""


def _parse_constraint(lines: list[str], i: int, constraint_type: str) -> tuple[int, "InpConstraint | None"]:
    """Parse a generic constraint keyword block.

    Captures the keyword line, data lines, and any constraint sub-keywords
    (e.g. ``*Kinematic``, ``*Distributing``, ``*Beam``).  Reading stops at
    the next unrelated keyword.
    """
    kw_line = lines[i].rstrip()
    params = _parse_parameters(kw_line)

    # Extract name: most use name=, Coupling uses constraint name=
    name = params.get("name", params.get("constraint name", ""))

    i += 1
    data_lines: list[str] = []

    while i < len(lines):
        trimmed = lines[i].lstrip()
        if _is_comment(trimmed) or not trimmed:
            i += 1
            continue
        if not trimmed.startswith("*"):
            # Data line (surface pair, etc.)
            data_lines.append(lines[i])
            i += 1
            continue
        # It's a * line — check whether it is a constraint sub-keyword
        sub = trimmed[1:].split(",")[0].strip().lower()
        if sub in ("kinematic", "distributing", "beam", "continuum distributing"):
            data_lines.append(lines[i])
            i += 1
            continue
        # Not a sub-keyword — stop
        break

    constraint = InpConstraint(
        type=constraint_type,
        name=name,
        keyword_line=kw_line,
        data_lines=data_lines,
    )
    return i, constraint


def _parse_assembly(lines: list[str], i: int, model: InpFileModel) -> int:
    """Parse the ``*Assembly ... *End Assembly`` block."""
    if i >= len(lines) or not _is_keyword(lines[i], "Assembly"):
        return i

    asm_params = _parse_parameters(lines[i])
    model.assembly_name = asm_params.get("name", "")

    assembly_start = i
    i += 1  # skip *Assembly

    while i < len(lines) and not _is_keyword(lines[i], "End Assembly"):
        line = lines[i]
        trimmed = line.lstrip()

        if _is_comment(trimmed) or not trimmed:
            i += 1
            continue

        if not trimmed.startswith("*"):
            # Data line — handled within sub-parsers; standalone lines skipped
            i += 1
            continue

        if _is_keyword(line, "Instance"):
            i, inst = _parse_instance(lines, i)
            if inst is not None:
                model.assembly_instances.append(inst)

        elif _is_keyword(line, "Node"):
            i = _parse_nodes(lines, i, model.assembly_ref_nodes)

        elif _is_keyword(line, "Nset"):
            i, nset = _parse_set(lines, i, "nset")
            if nset is not None:
                model.assembly_nsets.append(nset)

        elif _is_keyword(line, "Elset"):
            i, elset = _parse_assembly_elset(lines, i)
            if elset is not None:
                model.assembly_elsets.append(elset)

        elif _is_keyword(line, "Surface"):
            i, surf = _parse_surface(lines, i)
            if surf is not None:
                model.assembly_surfaces.append(surf)

        else:
            constraint_type = _is_assembly_constraint(line)
            if constraint_type:
                i, constraint = _parse_constraint(lines, i, constraint_type)
                if constraint is not None:
                    model.assembly_constraints.append(constraint)
                    # Backward compat: also populate assembly_couplings for Coupling
                    if constraint_type == "Coupling":
                        cp_params = _parse_parameters(line)
                        coupling = InpCoupling(
                            name=cp_params.get("constraint name", ""),
                            ref_node_set=cp_params.get("ref node", ""),
                            surface=cp_params.get("surface", ""),
                            constraint_type=constraint.data_lines[0] if constraint.data_lines else "",
                        )
                        model.assembly_couplings.append(coupling)
                continue
            # Unknown keyword in Assembly — preserve keyword + data lines as-is
            # Catches *Element, type=MASS, *Mass, *Spring, etc.
            block_lines: list[str] = [line]
            i += 1
            while i < len(lines) and not _is_keyword(lines[i], "End Assembly"):
                trimmed = lines[i].lstrip()
                if not trimmed:
                    i += 1
                    continue
                if trimmed.startswith("*") and not trimmed.startswith("**"):
                    break  # next keyword
                if _is_comment(trimmed):
                    i += 1
                    continue
                # Data line
                if lines[i].strip():
                    block_lines.append(lines[i])
                i += 1
            model.assembly_unknown_blocks.append(block_lines)
            continue

    # Collect raw Assembly lines for passthrough
    end = min(i + 1 if i < len(lines) else i, len(lines))
    for j in range(assembly_start, end):
        model.assembly_lines.append(lines[j])

    # Skip *End Assembly
    if i < len(lines):
        i += 1

    return i


# ── Phase 4: Material/Step ───────────────────────────────────────────────────


def _parse_material_step(lines: list[str], i: int, model: InpFileModel) -> int:
    """Collect all remaining lines (Material, Step, etc.) after ``*End Assembly``."""
    while i < len(lines):
        model.material_step_lines.append(lines[i])
        i += 1
    return i


# ── Sub-parsers ───────────────────────────────────────────────────────────────


def _parse_nodes(lines: list[str], i: int, nodes: list[InpNode]) -> int:
    """
    Read data lines after ``*Node``.
    Each line: ``id, x, y, z`` (4 comma-separated values).
    """
    i += 1
    while i < len(lines):
        trimmed = lines[i].lstrip()
        if trimmed.startswith("*") or _is_comment(trimmed):
            break

        if lines[i].strip():
            parts = lines[i].split(",")
            if len(parts) >= 4:
                try:
                    node = InpNode(
                        id=int(parts[0].strip()),
                        x=float(parts[1].strip()),
                        y=float(parts[2].strip()),
                        z=float(parts[3].strip()),
                    )
                    nodes.append(node)
                except (ValueError, IndexError):
                    pass  # skip malformed line gracefully
        i += 1
    return i


def _parse_elements(lines: list[str], i: int, elements: list[InpElement]) -> int:
    """
    Read data lines after ``*Element``.
    Each line: ``id, n1, n2, ...`` (first value is element ID, rest are node IDs).
    """
    i += 1
    while i < len(lines):
        trimmed = lines[i].lstrip()
        if trimmed.startswith("*") or _is_comment(trimmed):
            break

        if lines[i].strip():
            parts = lines[i].split(",")
            if len(parts) >= 2:
                try:
                    elem_id = int(parts[0].strip())
                    node_ids = [int(p.strip()) for p in parts[1:]]
                    elements.append(InpElement(id=elem_id, node_ids=node_ids))
                except (ValueError, IndexError):
                    pass  # skip malformed line gracefully
        i += 1
    return i


def _parse_set(lines: list[str], i: int, name_param: str) -> tuple[int, "InpSet | None"]:
    """
    Parse ``*Nset`` or ``*Elset`` (Part-level or Assembly-level Nset).

    :param name_param: Either ``"nset"`` or ``"elset"`` — the parameter holding the set name.
    :return: Tuple of (new_index, parsed set or None).
    """
    params = _parse_parameters(lines[i])
    set_name = params.get(name_param, "")
    is_generate = "generate" in params

    set_obj = InpSet(name=set_name, is_generate=is_generate, keyword_line=lines[i].rstrip())

    i += 1

    if is_generate:
        # Read single data line: start, end, step
        while i < len(lines):
            trimmed = lines[i].lstrip()
            if trimmed.startswith("*") or _is_comment(trimmed):
                break

            if lines[i].strip():
                parts = lines[i].split(",")
                if len(parts) >= 2:
                    try:
                        set_obj.start = int(parts[0].strip())
                    except (ValueError, IndexError):
                        pass
                    try:
                        set_obj.end = int(parts[1].strip())
                    except (ValueError, IndexError):
                        pass
                    set_obj.step = 1
                    if len(parts) >= 3:
                        try:
                            set_obj.step = int(parts[2].strip())
                        except (ValueError, IndexError):
                            pass
                i += 1
                return i, set_obj
            i += 1
    else:
        # Read data lines with IDs (up to 16 per line)
        while i < len(lines):
            trimmed = lines[i].lstrip()
            if trimmed.startswith("*") or _is_comment(trimmed):
                break

            if lines[i].strip():
                for val in lines[i].split(","):
                    val = val.strip()
                    try:
                        set_obj.ids.append(int(val))
                    except ValueError:
                        pass  # skip non-numeric tokens gracefully
            i += 1

    return i, set_obj


def _parse_assembly_elset(lines: list[str], i: int) -> tuple[int, "InpAssemblyElset | None"]:
    """
    Parse Assembly-level ``*Elset``.
    Captures keyword_line and data_lines for faithful reproduction.
    """
    keyword_line = lines[i]
    params = _parse_parameters(keyword_line)
    elset_name = params.get("elset", "")
    is_generate = "generate" in params
    is_internal = "internal" in params
    instance_name = params.get("instance")  # None if absent

    elset = InpAssemblyElset(
        name=elset_name,
        is_generate=is_generate,
        is_internal=is_internal,
        instance_name=instance_name,
        keyword_line=keyword_line,
    )

    i += 1

    if is_generate:
        while i < len(lines):
            trimmed = lines[i].lstrip()
            if trimmed.startswith("*") or _is_comment(trimmed):
                break

            if lines[i].strip():
                elset.data_lines.append(lines[i])
                parts = lines[i].split(",")
                if len(parts) >= 2:
                    try:
                        elset.start = int(parts[0].strip())
                    except (ValueError, IndexError):
                        pass
                    try:
                        elset.end = int(parts[1].strip())
                    except (ValueError, IndexError):
                        pass
                    elset.step = 1
                    if len(parts) >= 3:
                        try:
                            elset.step = int(parts[2].strip())
                        except (ValueError, IndexError):
                            pass
                i += 1
                return i, elset
            i += 1
    else:
        while i < len(lines):
            trimmed = lines[i].lstrip()
            if trimmed.startswith("*") or _is_comment(trimmed):
                break

            if lines[i].strip():
                elset.data_lines.append(lines[i])
                for val in lines[i].split(","):
                    val = val.strip()
                    try:
                        elset.ids.append(int(val))
                    except ValueError:
                        pass
            i += 1

    return i, elset


def _parse_instance(lines: list[str], i: int) -> tuple[int, "InpInstance | None"]:
    """
    Parse ``*Instance`` block.
    Captures name, part_name, and optional offset coordinates.
    """
    params = _parse_parameters(lines[i])
    name = params.get("name", "")
    part_name = params.get("part", "")

    instance = InpInstance(name=name, part_name=part_name)

    i += 1

    # Check for offset data line (x, y, z) before *End Instance
    while i < len(lines):
        trimmed = lines[i].lstrip()

        if _is_keyword(lines[i], "End Instance"):
            i += 1
            break

        if _is_comment(trimmed) or not trimmed:
            i += 1
            continue

        if trimmed.startswith("*"):
            # Unexpected keyword before *End Instance — stop
            break

        # Try to parse offset coordinates
        parts = lines[i].split(",")
        if len(parts) >= 3:
            try:
                instance.offset_x = float(parts[0].strip())
                instance.offset_y = float(parts[1].strip())
                instance.offset_z = float(parts[2].strip())
                instance.has_offset = True
                i += 1
                # Check for *End Instance on next line
                if i < len(lines) and _is_keyword(lines[i], "End Instance"):
                    i += 1
                break
            except (ValueError, IndexError):
                pass
        i += 1
        break

    return i, instance


def _parse_surface(lines: list[str], i: int) -> tuple[int, "InpSurface | None"]:
    """
    Parse ``*Surface`` block.
    Reads face entries of the form ``elset_name, face_label``.
    """
    params = _parse_parameters(lines[i])
    name = params.get("name", "")
    type_val = params.get("type", "")

    surface = InpSurface(name=name, type=type_val, keyword_line=lines[i].rstrip())

    i += 1

    # Read face entries until next keyword
    while i < len(lines):
        trimmed = lines[i].lstrip()
        if trimmed.startswith("*") or _is_comment(trimmed):
            break

        if lines[i].strip():
            parts = lines[i].split(",")
            if len(parts) >= 2:
                surface.entries.append(
                    InpSurfaceEntry(
                        elset_name=parts[0].strip(),
                        face_label=parts[1].strip(),
                    )
                )
        i += 1

    return i, surface


def _parse_coupling(lines: list[str], i: int) -> tuple[int, "InpCoupling | None"]:
    """
    Parse ``*Coupling`` block.
    Captures constraint name, ref node set, surface, and the constraint type keyword.
    """
    params = _parse_parameters(lines[i])
    name = params.get("constraint name", "")
    ref_node = params.get("ref node", "")
    surface_val = params.get("surface", "")

    coupling = InpCoupling(name=name, ref_node_set=ref_node, surface=surface_val)

    i += 1

    # Read constraint type keyword (e.g. *Kinematic) on next line
    while i < len(lines):
        trimmed = lines[i].lstrip()

        if _is_comment(trimmed) or not trimmed:
            i += 1
            continue

        if trimmed.startswith("*"):
            coupling.constraint_type = trimmed
            i += 1
            break

        # Data line — skip
        i += 1

    return i, coupling


# ── Keyword and parameter helpers ────────────────────────────────────────────


def _is_keyword(line: str, keyword: str) -> bool:
    """
    Check whether *line* starts with the specified INP keyword.

    Ensures exact keyword match so that, for example, ``"Element"``
    does not match ``"*Elset"``.

    Expects *keyword* **without** the leading ``*`` (e.g. ``"Part"``,
    ``"End Assembly"``).  The function itself prepends ``*`` for matching.

    :param line: Raw INP file line (may have leading whitespace).
    :param keyword: Keyword to match (e.g. ``"Part"``, ``"Solid Section"``).
    :return: ``True`` if the line is that keyword line.
    """
    if not line:
        return False
    trimmed = line.lstrip()
    if not trimmed.startswith("*"):
        return False

    rest = trimmed[1:]  # skip '*'

    # Case-insensitive prefix match
    if not rest.lower().startswith(keyword.lower()):
        return False

    if len(rest) == len(keyword):
        return True

    next_char = rest[len(keyword)]
    return next_char in (",", " ", "\t")


def _parse_parameters(line: str) -> dict[str, str]:
    """
    Extract comma-separated ``key=value`` parameters from a keyword line.

    Handles:
      - key=value pairs
      - flag parameters without ``=`` (e.g. ``generate``, ``internal``)
      - multi-word parameter names (e.g. ``constraint name``, ``ref node``)

    :param line: A keyword line (e.g. ``"*Part, name=Part-1"``).
    :return: Dictionary of parameter names to their values. Keys are lowercased
             for case-insensitive lookup.
    """
    result: dict[str, str] = {}
    if not line:
        return result

    trimmed = line.lstrip()
    first_comma = trimmed.find(",")
    if first_comma < 0:
        return result

    param_section = trimmed[first_comma + 1 :].strip()
    if not param_section:
        return result

    for part in param_section.split(","):
        p = part.strip()
        if not p:
            continue

        eq_index = p.find("=")
        if eq_index >= 0:
            key = p[:eq_index].strip()
            value = p[eq_index + 1 :].strip()
            if key:
                result[key.lower()] = value
        else:
            # Flag without value (e.g. "generate", "internal")
            result[p.lower()] = ""

    return result


def _is_comment(trimmed_line: str) -> bool:
    """
    Check whether a trimmed line is an INP comment (starts with ``**``).

    :param trimmed_line: A line that has already been left-stripped.
    :return: ``True`` if the line is a comment.
    """
    return trimmed_line.startswith("**")
