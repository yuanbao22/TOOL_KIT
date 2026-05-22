"""
Merge engine for combining two Abaqus INP files via a 6-phase pipeline.

6-phase pipeline:
  Phase 1: Read + parse file1, compute node/element offsets from max IDs
  Phase 2: Write file1 heading lines to output
  Phase 3: Write file1 parts (offset=0, no renumbering)
  Phase 4: Read + parse file2, write parts (renumbered with offsets)
  Phase 5: Write merged Assembly (instances, ref nodes, nsets, elsets,
           surfaces, couplings with conflict resolution & renaming)
  Phase 6: Merge material/step sections from both files with conflict
           resolution (material/step dedup, BC/load renumbering,
           output dedup).

Maps 1:1 from the C# InpMergeService.WriteAssembly logic.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import inp_parser, inp_writer
from .models import InpAssemblyElset, InpConstraint, InpCoupling, InpFileModel, InpInstance, InpNode, InpSet, InpSurface, MergeResult


# ═══════════════════════════════════════════════════════════════════
#  Internal types for material/step block parsing
# ═══════════════════════════════════════════════════════════════════


@dataclass
class _TopBlock:
    """A top-level block in the material/step section.

    Attributes:
        type: One of ``"material"``, ``"step"``, or ``"other"``.
        name: The block name (e.g. material name, step name).
        lines: All raw lines belonging to this block.
    """
    type: str = ""          # "material" | "step" | "other"
    name: str = ""          # name parameter value
    lines: list[str] = field(default_factory=list)


@dataclass
class _StepSubBlock:
    """A sub-block within a parsed step.

    Attributes:
        category: ``"boundary"`` | ``"load"`` | ``"output_field"``
                  | ``"output_history"`` | ``"other"``
        name: The ``name=`` parameter value (empty if none).
        lines: All raw lines of this sub-block.
    """
    category: str = ""      # see above
    name: str = ""          # name parameter value
    lines: list[str] = field(default_factory=list)


# Keywords that normally carry a ``name=`` parameter and represent
# loading conditions within a step.
_LOAD_KEYWORDS = frozenset({
    "Cload", "Dload", "Dsload", "Cflux", "Dsflux", "Dflux",
    "Film", "Radiation",
})

# Sub-keywords that belong to a parent keyword block (not separate blocks).
# Used so *Node Output / *Element Output under *Output are kept as
# data lines rather than becoming independent sub-blocks.
_OUTPUT_SUB_KEYWORDS = frozenset({
    "Node Output", "Element Output", "Contact Output",
    "Section Output",
})


class MergeEngine:
    """Orchestrates the 6-phase INP file merge pipeline."""

    def __init__(self, log_callback: Optional[Callable[[str], None]] = None) -> None:
        """
        Initialise the merge engine.

        Args:
            log_callback: Optional callback that receives log messages.
                          When None, messages are printed to stdout.
        """
        self._log_callback: Optional[Callable[[str], None]] = log_callback
        # Name maps built during Phase 5, consumed by Phase 6 for Boundary/Cload set name updates
        self._nset_name_map: dict[str, str] = {}
        self._instance_name_map: dict[str, str] = {}
        # Part-level nset rename map built during Phase 4, merged into _nset_name_map at Phase 5
        self._part_nset_name_map: dict[str, str] = {}

    @property
    def log_callback(self) -> Optional[Callable[[str], None]]:
        return self._log_callback

    @log_callback.setter
    def log_callback(self, value: Optional[Callable[[str], None]]) -> None:
        self._log_callback = value

    # ------------------------------------------------------------------
    #  Logging
    # ------------------------------------------------------------------

    def _log(self, msg: str) -> None:
        """Emit a log message via the callback or stdout."""
        if self._log_callback is not None:
            self._log_callback(msg)
        else:
            print(msg)

    # ------------------------------------------------------------------
    #  ID-line formatting (16 values per line per Abaqus convention)
    # ------------------------------------------------------------------

    @staticmethod
    def _write_id_lines(ids: list[int]) -> list[str]:
        """Format ID values as comma-separated lines, max 16 per line."""
        lines: list[str] = []
        max_per_line = 16
        for offset in range(0, len(ids), max_per_line):
            chunk = ids[offset : offset + max_per_line]
            line = ", ".join(str(v) for v in chunk)
            if len(chunk) == 1 and offset + len(chunk) == len(ids):
                line += ","
            lines.append(line)
        return lines

    # ------------------------------------------------------------------
    #  Main entry point
    # ------------------------------------------------------------------

    async def merge(
        self,
        file1_path: str,
        file2_path: str,
        output_path: str,
    ) -> MergeResult:
        """
        Execute the full 6-phase merge pipeline.

        Args:
            file1_path: Path to the first (base) INP file.
            file2_path: Path to the second INP file to merge in.
            output_path: Path where the merged INP file will be written.

        Returns:
            MergeResult with success flag, offsets, and status message.
        """
        result = MergeResult()

        try:
            path1 = Path(file1_path)
            path2 = Path(file2_path)

            if not path1.exists():
                raise FileNotFoundError(f"File not found: {file1_path}")
            if not path2.exists():
                raise FileNotFoundError(f"File not found: {file2_path}")

            # ---- Phase 1: Read + parse file1, compute offsets ---------
            self._log(f"Reading file 1: {file1_path}")
            lines1 = path1.read_text(encoding="ascii").splitlines()
            self._log(f"  → {len(lines1)} lines")

            model1: InpFileModel = inp_parser.parse(lines1)
            existing_names: set[str] = {p.name for p in model1.parts}

            node_offset = 0
            elem_offset = 0
            for part in model1.parts:
                if part.nodes:
                    node_offset = max(node_offset, max(n.id for n in part.nodes))
                if part.elements:
                    elem_offset = max(elem_offset, max(e.id for e in part.elements))

            result.node_offset = node_offset
            result.elem_offset = elem_offset
            self._log(f"Node offset: {node_offset}, Element offset: {elem_offset}")

            # ---- Build output lines -------------------------------------
            output_lines: list[str] = []

            # Phase 2: Write heading
            self._log("Phase 2: Writing heading...")
            output_lines.extend(model1.heading_lines)

            # Phase 3: Write file1 parts (no renumbering)
            self._log("Phase 3: Writing file1 parts...")
            for part in model1.parts:
                output_lines.extend(inp_writer.write_part(part, 0, 0))
            self._log(f"  {len(model1.parts)} part(s) written from file 1")

            # Phase 4: Read + parse file2, write parts (renumbered)
            self._log(f"Reading file 2: {file2_path}")
            lines2 = path2.read_text(encoding="ascii").splitlines()
            self._log(f"  → {len(lines2)} lines")

            model2: InpFileModel = inp_parser.parse(lines2)

            # Collect all part-level elset, nset and orientation names from file1
            # for conflict detection (requirement: rename duplicates, no dedup)
            file1_part_elset_names: set[str] = set()
            file1_part_nset_names: set[str] = set()
            file1_part_orient_names: set[str] = set()
            for part in model1.parts:
                for elset in part.elsets:
                    file1_part_elset_names.add(elset.name)
                for nset in part.nsets:
                    file1_part_nset_names.add(nset.name)
                for orient in part.orientations:
                    file1_part_orient_names.add(orient.name)

            self._log("Phase 4: Writing file2 parts (renumbered)...")
            all_part_nset_renames: dict[str, str] = {}
            for part in model2.parts:
                if part.name in existing_names:
                    part.name += "-2"

                # Resolve elset name conflicts - rename duplicates, keep ALL (no dedup)
                elset_rename: dict[str, str] = {}
                for elset in part.elsets:
                    if elset.name in file1_part_elset_names:
                        counter = 2
                        new_name = f"{elset.name}_{counter}"
                        while new_name in file1_part_elset_names:
                            counter += 1
                            new_name = f"{elset.name}_{counter}"
                        elset_rename[elset.name] = new_name
                        self._log(
                            f"    → Renamed part elset: {elset.name} → {new_name}"
                        )
                        # Update keyword_line to reflect new name
                        elset.keyword_line = elset.keyword_line.replace(
                            f"elset={elset.name}", f"elset={new_name}"
                        )
                        elset.name = new_name
                    file1_part_elset_names.add(elset.name)

                # Resolve nset name conflicts - rename duplicates, keep ALL (no dedup)
                part_nset_rename: dict[str, str] = {}
                for nset in part.nsets:
                    if nset.name in file1_part_nset_names:
                        counter = 2
                        new_name = f"{nset.name}_{counter}"
                        while new_name in file1_part_nset_names:
                            counter += 1
                            new_name = f"{nset.name}_{counter}"
                        part_nset_rename[nset.name] = new_name
                        self._log(
                            f"    → Renamed part nset: {nset.name} → {new_name}"
                        )
                        # Update keyword_line to reflect new name
                        if nset.keyword_line:
                            nset.keyword_line = nset.keyword_line.replace(
                                f"nset={nset.name}", f"nset={new_name}"
                            )
                        nset.name = new_name
                    file1_part_nset_names.add(nset.name)
                all_part_nset_renames.update(part_nset_rename)

                # Resolve orientation name conflicts - rename duplicates, keep ALL (no dedup)
                orient_rename: dict[str, str] = {}
                for orient in part.orientations:
                    old_name = orient.name
                    if old_name in file1_part_orient_names:
                        counter = 2
                        new_name = f"{old_name}_{counter}"
                        while new_name in file1_part_orient_names:
                            counter += 1
                            new_name = f"{old_name}_{counter}"
                        orient_rename[old_name] = new_name
                        self._log(
                            f"    → Renamed part orientation: {old_name} → {new_name}"
                        )
                        orient.name = new_name
                        if orient.lines:
                            orient.lines[0] = orient.lines[0].replace(
                                f"name={old_name}", f"name={new_name}"
                            )
                    file1_part_orient_names.add(orient.name)

                # Update shell section references for renamed elsets and orientations
                for idx, line in enumerate(part.shell_section_lines):
                    new_line = line
                    if "elset=" in new_line.lower():
                        ref = self._get_param(new_line, "elset")
                        if ref in elset_rename:
                            new_line = new_line.replace(
                                f"elset={ref}", f"elset={elset_rename[ref]}"
                            )
                    if "orientation=" in new_line.lower():
                        ref = self._get_param(new_line, "orientation")
                        if ref in orient_rename:
                            new_line = new_line.replace(
                                f"orientation={ref}",
                                f"orientation={orient_rename[ref]}",
                            )
                    if "nset=" in new_line.lower():
                        ref = self._get_param(new_line, "nset")
                        if ref in part_nset_rename:
                            new_line = new_line.replace(
                                f"nset={ref}", f"nset={part_nset_rename[ref]}"
                            )
                    part.shell_section_lines[idx] = new_line

                # Update solid section references for renamed elsets and nsets
                for idx, line in enumerate(part.solid_section_lines):
                    if "elset=" in line.lower():
                        ref = self._get_param(line, "elset")
                        if ref in elset_rename:
                            part.solid_section_lines[idx] = line.replace(
                                f"elset={ref}", f"elset={elset_rename[ref]}"
                            )
                    if "nset=" in line.lower():
                        ref = self._get_param(line, "nset")
                        if ref in part_nset_rename:
                            part.solid_section_lines[idx] = line.replace(
                                f"nset={ref}", f"nset={part_nset_rename[ref]}"
                            )

                # Update unknown/preserved block references for renamed elsets,
                # nsets, and orientations (*Beam Section, *Spring, etc.)
                for blk_idx, block in enumerate(part.unknown_block_lines):
                    updated_block: list[str] = []
                    for line in block:
                        new_line = line
                        if "elset=" in new_line.lower():
                            ref = self._get_param(new_line, "elset")
                            if ref in elset_rename:
                                new_line = new_line.replace(
                                    f"elset={ref}", f"elset={elset_rename[ref]}"
                                )
                        if "nset=" in new_line.lower():
                            ref = self._get_param(new_line, "nset")
                            if ref in part_nset_rename:
                                new_line = new_line.replace(
                                    f"nset={ref}", f"nset={part_nset_rename[ref]}"
                                )
                        if "orientation=" in new_line.lower():
                            ref = self._get_param(new_line, "orientation")
                            if ref in orient_rename:
                                new_line = new_line.replace(
                                    f"orientation={ref}",
                                    f"orientation={orient_rename[ref]}",
                                )
                        updated_block.append(new_line)
                    part.unknown_block_lines[blk_idx] = updated_block

                output_lines.extend(
                    inp_writer.write_part(part, node_offset, elem_offset)
                )
            self._log(
                f"  {len(model2.parts)} part(s) written from file 2 "
                f"(nodes +{node_offset}, elements +{elem_offset})"
            )
            if all_part_nset_renames:
                self._part_nset_name_map = all_part_nset_renames
                self._log(
                    f"  {len(all_part_nset_renames)} part-level nset(s) renamed"
                )

            # Phase 5: Write merged Assembly
            self._log("Phase 5: Writing merged Assembly...")
            self._write_assembly(
                output_lines, model1, model2, node_offset, elem_offset, existing_names
            )

            # Phase 6: Merge material/step sections
            self._log("Phase 6: Merging material/step...")
            self._merge_material_step(output_lines, model1, model2)

            # ---- Write output file --------------------------------------
            Path(output_path).write_text(
                "\n".join(output_lines) + "\n", encoding="ascii"
            )

            result.success = True
            result.output_path = output_path
            result.message = "Merge completed successfully"
            self._log(f"Merge completed → {output_path}")

        except Exception as e:
            result.message = f"Merge failed: {e}"
            self._log(f"ERROR: {e}")

        return result

    # ------------------------------------------------------------------
    #  Phase 5: Write merged Assembly
    # ------------------------------------------------------------------

    def _write_assembly(
        self,
        output_lines: list[str],
        model1: InpFileModel,
        model2: InpFileModel,
        node_offset: int,
        elem_offset: int,
        file1_part_names: set[str],
    ) -> None:
        """
        Write the merged Assembly section.

        Order: instances, reference nodes, nsets, elsets, surfaces, couplings.

        For model2 entries:
          - Node IDs are increased by *node_offset*.
          - Duplicate names across the two files are resolved with
            ``_N`` suffixes, and name-maps are threaded through to
            downstream references (elsets → surfaces, surfaces → couplings,
            nsets → couplings).
        """
        # Header
        output_lines.append("**  ")
        output_lines.append("**")
        output_lines.append("** ASSEMBLY")
        output_lines.append("**")
        output_lines.append("*Assembly, name=Assembly")
        output_lines.append("**  ")

        instance_count = 0

        # --- Instances --------------------------------------------------
        # File 1 instance names (tracked to detect conflicts)
        instance_names_1: set[str] = set()

        # File 1 instances (as-is)
        for inst in model1.assembly_instances:
            instance_names_1.add(inst.name)
            output_lines.append(f"*Instance, name={inst.name}, part={inst.part_name}")
            if inst.has_offset:
                output_lines.append(
                    f"       {inst.offset_x:g}, {inst.offset_y:g}, {inst.offset_z:g}"
                )
            output_lines.append("*End Instance")
            output_lines.append("**  ")
            instance_count += 1

        # File 2 instances (resolve name + part conflicts)
        instance_name_map: dict[str, str] = {}
        for inst in model2.assembly_instances:
            # Rename instance if its name already exists in file1
            new_inst_name = inst.name
            if inst.name in instance_names_1:
                new_inst_name = f"{inst.name}-2"
                self._log(
                    f"    → Renamed instance: {inst.name} → {new_inst_name}"
                )
            instance_name_map[inst.name] = new_inst_name

            # Update part reference (part may have been renamed too)
            part_name = (
                inst.part_name + "-2"
                if inst.part_name in file1_part_names
                else inst.part_name
            )
            output_lines.append(
                f"*Instance, name={new_inst_name}, part={part_name}"
            )
            if inst.has_offset:
                output_lines.append(
                    f"       {inst.offset_x:g}, {inst.offset_y:g}, {inst.offset_z:g}"
                )
            output_lines.append("*End Instance")
            output_lines.append("**  ")
            instance_count += 1

        # --- Reference nodes --------------------------------------------
        has_ref_nodes = (
            len(model1.assembly_ref_nodes) > 0
            or len(model2.assembly_ref_nodes) > 0
        )
        if has_ref_nodes:
            output_lines.append("*Node")
            # File 1 ref nodes (original IDs)
            for node in model1.assembly_ref_nodes:
                output_lines.append(
                    f"{node.id}, {node.x:g}, {node.y:g}, {node.z:g}"
                )
            # File 2 ref nodes (IDs + node_offset)
            for node in model2.assembly_ref_nodes:
                output_lines.append(
                    f"{node.id + node_offset}, {node.x:g}, {node.y:g}, {node.z:g}"
                )

        # --- Nsets ------------------------------------------------------
        # File 1 nsets
        nset_name_counts: dict[str, int] = {}
        for nset in model1.assembly_nsets:
            nset_name_counts[nset.name] = 1
            self._write_nset(output_lines, nset, 0, nset.name)

        # File 2 nsets (renumber IDs, rename duplicates)
        nset_name_map: dict[str, str] = {}
        for nset in model2.assembly_nsets:
            new_name = nset.name
            if nset.name in nset_name_counts:
                nset_name_counts[nset.name] += 1
                new_name = f"{nset.name}_{nset_name_counts[nset.name]}"
            else:
                nset_name_counts[nset.name] = 1
            nset_name_map[nset.name] = new_name
            self._write_nset(
                output_lines, nset, node_offset, new_name, instance_name_map
            )

        # --- Elsets -----------------------------------------------------
        # File 1 elsets (write keyword_line + data_lines as-is)
        elset_name_counts: dict[str, int] = {}
        for elset in model1.assembly_elsets:
            elset_name_counts[elset.name] = 1
            output_lines.append(elset.keyword_line)
            output_lines.extend(elset.data_lines)

        # File 2 elsets (rename duplicates, update keyword_line)
        elset_name_map: dict[str, str] = {}
        for elset in model2.assembly_elsets:
            new_name = elset.name
            if elset.name in elset_name_counts:
                elset_name_counts[elset.name] += 1
                new_name = f"{elset.name}_{elset_name_counts[elset.name]}"
            else:
                elset_name_counts[elset.name] = 1
            elset_name_map[elset.name] = new_name

            # Replace elset=... and instance=... in the keyword line
            # with renamed values
            new_keyword_line = elset.keyword_line
            new_keyword_line = new_keyword_line.replace(
                f"elset={elset.name}", f"elset={new_name}"
            )
            if elset.instance_name and elset.instance_name in instance_name_map:
                new_keyword_line = new_keyword_line.replace(
                    f"instance={elset.instance_name}",
                    f"instance={instance_name_map[elset.instance_name]}",
                )
            output_lines.append(new_keyword_line)
            output_lines.extend(elset.data_lines)

        # --- Surfaces ---------------------------------------------------
        # File 1 surfaces
        surface_name_counts: dict[str, int] = {}
        for surf in model1.assembly_surfaces:
            surface_name_counts[surf.name] = 1
            # Use original keyword_line to preserve internal etc.
            if surf.keyword_line:
                output_lines.append(surf.keyword_line)
            else:
                output_lines.append(f"*Surface, type={surf.type}, name={surf.name}")
            for entry in surf.entries:
                output_lines.append(f"{entry.elset_name}, {entry.face_label}")

        # File 2 surfaces (rename duplicates, remap elset references)
        surface_name_map: dict[str, str] = {}
        for surf in model2.assembly_surfaces:
            new_name = surf.name
            if surf.name in surface_name_counts:
                surface_name_counts[surf.name] += 1
                new_name = f"{surf.name}_{surface_name_counts[surf.name]}"
            else:
                surface_name_counts[surf.name] = 1
            surface_name_map[surf.name] = new_name

            # Use original keyword_line with name replaced
            if surf.keyword_line and surf.name:
                kw = surf.keyword_line.replace(f"name={surf.name}", f"name={new_name}")
                output_lines.append(kw)
            else:
                output_lines.append(f"*Surface, type={surf.type}, name={new_name}")
            for entry in surf.entries:
                # NODE-type surfaces reference nsets; ELEMENT-type reference elsets
                if surf.type and surf.type.upper() == "NODE":
                    new_ref_name = nset_name_map.get(
                        entry.elset_name, entry.elset_name
                    )
                else:
                    new_ref_name = elset_name_map.get(
                        entry.elset_name, entry.elset_name
                    )
                output_lines.append(f"{new_ref_name}, {entry.face_label}")

        # --- Constraints (Tie, Rigid Body, Display Body, Coupling, etc.) --
        # File 1 constraints
        constraint_name_counts: dict[str, int] = {}
        for constraint in model1.assembly_constraints:
            if constraint.name:
                constraint_name_counts[constraint.name] = 1
            output_lines.append(constraint.keyword_line)
            if constraint.data_lines:
                output_lines.extend(constraint.data_lines)

        # File 2 constraints (rename duplicates, remap references)
        for constraint in model2.assembly_constraints:
            name = constraint.name
            new_keyword = constraint.keyword_line

            # Rename on conflict (only if the constraint has a name)
            if name and name in constraint_name_counts:
                constraint_name_counts[name] += 1
                new_name = f"{name}_{constraint_name_counts[name]}"
                # Replace name= or constraint name= in keyword line
                for param in ("constraint name=", "name="):
                    old_val = f"{param}{name}"
                    new_val = f"{param}{new_name}"
                    if old_val in new_keyword:
                        new_keyword = new_keyword.replace(old_val, new_val)
                        break
            elif name:
                constraint_name_counts[name] = 1

            # Update surface/nset/elset references in keyword line
            new_keyword = self._update_refs_in_line(
                new_keyword, surface_name_map, nset_name_map, elset_name_map
            )

            output_lines.append(new_keyword)

            # Update data lines (e.g. *Tie surface pairs)
            if constraint.data_lines:
                updated_data = list(constraint.data_lines)
                # For *Tie, data lines are surface references
                if constraint.type == "Tie":
                    updated_data = self._update_tie_data_lines(
                        updated_data, surface_name_map
                    )
                output_lines.extend(updated_data)

        # --- Unknown assembly blocks (*Element, type=MASS, *Mass, etc.) ---
        # File 1 unknown blocks (as-is, original names and IDs)
        for block in model1.assembly_unknown_blocks:
            output_lines.extend(block)

        # File 2 unknown blocks (apply elset name mapping + ID offsets)
        for block in model2.assembly_unknown_blocks:
            if not block:
                continue
            first_line = block[0]
            # *Element, type=MASS / SPRING etc. — apply elset rename + ID offset
            if inp_parser._is_keyword(first_line, "Element"):
                kw = first_line
                if "elset=" in kw.lower():
                    ref = MergeEngine._get_param(kw, "elset")
                    if ref in elset_name_map:
                        kw = kw.replace(f"elset={ref}", f"elset={elset_name_map[ref]}")
                output_lines.append(kw)
                for data_line in block[1:]:
                    parts = [p.strip() for p in data_line.split(",")]
                    if len(parts) >= 2:
                        try:
                            elem_id = int(parts[0]) + elem_offset
                            node_id = int(parts[1]) + node_offset
                            rest = ", ".join(parts[2:])
                            output_lines.append(f"{elem_id}, {node_id}{', ' + rest if rest else ''}")
                        except ValueError:
                            output_lines.append(data_line)
                    else:
                        output_lines.append(data_line)
            elif inp_parser._is_keyword(first_line, "Mass"):
                # *Mass — apply elset rename only (mass values are scalars)
                kw = first_line
                if "elset=" in kw.lower():
                    ref = MergeEngine._get_param(kw, "elset")
                    if ref in elset_name_map:
                        kw = kw.replace(f"elset={ref}", f"elset={elset_name_map[ref]}")
                output_lines.append(kw)
                output_lines.extend(block[1:])
            elif inp_parser._is_keyword(first_line, "Spring"):
                # *Spring / *Spring Section — apply elset rename
                kw = first_line
                if "elset=" in kw.lower():
                    ref = MergeEngine._get_param(kw, "elset")
                    if ref in elset_name_map:
                        kw = kw.replace(f"elset={ref}", f"elset={elset_name_map[ref]}")
                output_lines.append(kw)
                output_lines.extend(block[1:])
            else:
                # Generic pass-through
                output_lines.extend(block)

        # Footer
        output_lines.append("*End Assembly")

        surface_total = len(surface_name_counts)
        constraint_total = len(model1.assembly_constraints) + len(model2.assembly_constraints)
        unknown_total = len(model1.assembly_unknown_blocks) + len(model2.assembly_unknown_blocks)
        self._log(
            f"  Assembly written: {instance_count} instance(s), "
            f"{surface_total} surface(s), {constraint_total} constraint(s)"
            f"{', ' + str(unknown_total) + ' unknown block(s)' if unknown_total else ''}"
        )

        # Store name maps for Phase 6 (Boundary/Cload set name updates)
        # Merge in part-level nset renames from Phase 4 (without overriding assembly-level)
        final_nset_map = dict(nset_name_map)
        if self._part_nset_name_map:
            for k, v in self._part_nset_name_map.items():
                if k not in final_nset_map:
                    final_nset_map[k] = v
        self._nset_name_map = final_nset_map
        self._instance_name_map = instance_name_map

    # ------------------------------------------------------------------
    #  Helper: extract a single parameter value from a keyword line
    # ------------------------------------------------------------------

    @staticmethod
    def _get_param(line: str, param_name: str) -> str:
        """
        Extract a parameter value from a keyword line (case-insensitive).

        Example::

            _get_param("*Boundary, type=DISPLACEMENT, name=BC-1", "name")
            # => "BC-1"

        Returns ``""`` if the parameter is not found.
        """
        target = param_name.lower()
        comma = line.find(",")
        if comma < 0:
            return ""
        for part in line[comma + 1:].split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                if k.strip().lower() == target:
                    return v.strip()
        return ""

    @staticmethod
    def _update_refs_in_line(
        line: str,
        surface_name_map: dict[str, str],
        nset_name_map: dict[str, str],
        elset_name_map: dict[str, str],
    ) -> str:
        """Update surface/nset/elset references in a constraint keyword line.

        Checks for the following parameters and replaces their values
        if they appear in the corresponding name map:
          - ``surface=``
          - ``ref node=``
          - ``elset=``
          - ``slave name=`` / ``master name=``
        """
        result = line
        # surface= — used by *Coupling, *Tie
        if "surface=" in result.lower():
            ref = MergeEngine._get_param(result, "surface")
            if ref in surface_name_map:
                result = result.replace(f"surface={ref}", f"surface={surface_name_map[ref]}")
        # ref node= — used by *Coupling, *Rigid Body
        if "ref node=" in result.lower():
            ref = MergeEngine._get_param(result, "ref node")
            if ref in nset_name_map:
                result = result.replace(f"ref node={ref}", f"ref node={nset_name_map[ref]}")
        # elset= — used by *Rigid Body, *Display Body
        if "elset=" in result.lower():
            ref = MergeEngine._get_param(result, "elset")
            if ref in elset_name_map:
                result = result.replace(f"elset={ref}", f"elset={elset_name_map[ref]}")
        # slave name= / master name= — used by *Tie
        for param in ("slave name=", "master name="):
            if param in result.lower():
                ref = MergeEngine._get_param(result, param.rstrip("="))
                if ref in nset_name_map:
                    result = result.replace(f"{param}{ref}", f"{param}{nset_name_map[ref]}")
        return result

    @staticmethod
    def _update_tie_data_lines(
        data_lines: list[str],
        surface_name_map: dict[str, str],
    ) -> list[str]:
        """Update surface references in *Tie data lines.

        *Tie data lines contain a pair of surface names::

            master_surface_name, slave_surface_name

        Each is replaced if it appears in *surface_name_map*.
        """
        result: list[str] = []
        for line in data_lines:
            new_line = line
            parts = [p.strip() for p in line.split(",")]
            for part in parts:
                if part in surface_name_map:
                    new_line = new_line.replace(part, surface_name_map[part])
            result.append(new_line)
        return result

    # ------------------------------------------------------------------
    #  Material/step block parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_restart_or_output_line(line: str) -> bool:
        """Check if *line* starts with *Restart or *Output keyword."""
        trimmed = line.lstrip().lower()
        return trimmed.startswith("*restart") or trimmed.startswith("*output")

    @staticmethod
    def _parse_top_blocks(lines: list[str]) -> list[_TopBlock]:
        """
        Split raw material/step lines into top-level blocks.

        Recognised blocks:
          - ``*Material, name=...``  (type ``"material"``)
          - ``*Step, name=...`` ... ``*End Step``  (type ``"step"``)
          - ``*Restart / *Output`` (type ``"other"``, each forms its own block)
          - Everything else  (type ``"other"``, passed through as-is)
        """
        blocks: list[_TopBlock] = []

        def _is_material(line: str) -> bool:
            return line.lstrip().startswith("*") and inp_parser._is_keyword(line, "Material")

        def _is_step(line: str) -> bool:
            return line.lstrip().startswith("*") and inp_parser._is_keyword(line, "Step")

        def _is_end_step(line: str) -> bool:
            return inp_parser._is_keyword(line, "End Step")

        buf: list[str] = []

        def _flush():
            if buf:
                blocks.append(_TopBlock(type="other", name="", lines=buf.copy()))
                buf.clear()

        i = 0
        while i < len(lines):
            line = lines[i]
            if _is_material(line):
                _flush()
                name = MergeEngine._get_param(line, "name")
                block_lines: list[str] = [line]
                i += 1
                while i < len(lines) and not _is_material(lines[i]) and not _is_step(lines[i]) and not MergeEngine._is_restart_or_output_line(lines[i]):
                    block_lines.append(lines[i])
                    i += 1
                blocks.append(_TopBlock(type="material", name=name, lines=block_lines))
            elif _is_step(line):
                _flush()
                name = MergeEngine._get_param(line, "name")
                block_lines = [line]
                i += 1
                while i < len(lines) and not _is_end_step(lines[i]):
                    block_lines.append(lines[i])
                    i += 1
                if i < len(lines):          # include *End Step
                    block_lines.append(lines[i])
                    i += 1
                blocks.append(_TopBlock(type="step", name=name, lines=block_lines))
            elif MergeEngine._is_restart_or_output_line(line):
                _flush()
                ro_lines: list[str] = [line]
                i += 1
                # Read data/sub-keyword lines until next top-level keyword
                while i < len(lines):
                    cline = lines[i]
                    trimmed = cline.lstrip()
                    if (
                        not trimmed
                        or trimmed.startswith("**")
                        or (trimmed.startswith("*") and
                            (inp_parser._is_keyword(cline, "Material") or
                             inp_parser._is_keyword(cline, "Step") or
                             MergeEngine._is_restart_or_output_line(cline)))
                    ):
                        break
                    if cline.strip():
                        ro_lines.append(cline)
                    i += 1
                blocks.append(_TopBlock(type="other", name="", lines=ro_lines))
            else:
                buf.append(line)
                i += 1

        _flush()
        return blocks

    # ── Load keyword detection ─────────────────────────────────────

    @staticmethod
    def _is_load_keyword(line: str) -> bool:
        """Check if *line* starts with a recognised load keyword."""
        trimmed = line.lstrip()
        if not trimmed.startswith("*"):
            return False
        rest = trimmed[1:]  # strip leading *
        # Extract the keyword name (up to first comma or whitespace)
        kw = rest.split(",")[0].strip().split()[0]
        return kw in _LOAD_KEYWORDS

    @staticmethod
    def _is_output_sub_keyword(line: str) -> bool:
        """Check if *line* is a sub-keyword of an output block
        (e.g. ``*Node Output``, ``*Element Output``)."""
        trimmed = line.lstrip()
        if not trimmed.startswith("*"):
            return False
        rest = trimmed[1:].lstrip()
        for sub_kw in _OUTPUT_SUB_KEYWORDS:
            if rest.lower().startswith(sub_kw.lower()):
                return True
        return False

    # ── Step sub-block parser ─────────────────────────────────────

    @staticmethod
    def _parse_step_sub_blocks(step_lines: list[str]) -> list[_StepSubBlock]:
        """
        Parse a step's body (everything between ``*Step`` and ``*End Step``)
        into sub-blocks.

        Classification rules:
          - ``*Boundary, name=...``  → category ``"boundary"``
          - Load keywords (see ``_LOAD_KEYWORDS``) with ``name=`` → ``"load"``
          - ``*Output, field`` → ``"output_field"``
          - ``*Output, history`` → ``"output_history"``
          - Everything else → ``"other"``
        """
        blocks: list[_StepSubBlock] = []
        i = 0

        def _is_sub_keyword(line: str) -> bool:
            """True if *line* starts a keyword (not comment, not *End Step)."""
            trimmed = line.lstrip()
            if not trimmed.startswith("*"):
                return False
            if trimmed.startswith("**"):
                return False
            if inp_parser._is_keyword(line, "End Step"):
                return False
            return True

        def _classify(line: str) -> tuple[str, str]:
            """Return (category, name) for a keyword line."""
            trimmed = line.lstrip()
            if inp_parser._is_keyword(line, "Boundary"):
                return ("boundary", MergeEngine._get_param(line, "name"))
            if MergeEngine._is_load_keyword(line):
                return ("load", MergeEngine._get_param(line, "name"))
            if trimmed.startswith("*Output") and not trimmed.startswith("**"):
                params = {}
                comma = trimmed.find(",")
                if comma >= 0:
                    for part in trimmed[comma + 1:].split(","):
                        if "=" in part:
                            k, v = part.split("=", 1)
                            params[k.strip().lower()] = v.strip()
                        else:
                            params[part.strip().lower()] = ""
                if "field" in params:
                    return ("output_field", "")
                if "history" in params:
                    return ("output_history", "")
                return ("output_other", "")
            return ("other", "")

        while i < len(step_lines):
            line = step_lines[i]
            trimmed = line.lstrip()
            if inp_parser._is_keyword(line, "End Step"):
                break
            if not trimmed or trimmed.startswith("**") or not _is_sub_keyword(line):
                # Non-keyword / comment content — group into an "other" block
                blk_lines: list[str] = []
                while i < len(step_lines):
                    cline = step_lines[i]
                    if (
                        inp_parser._is_keyword(cline, "End Step")
                        or _is_sub_keyword(cline)
                    ):
                        break
                    blk_lines.append(cline)
                    i += 1
                if blk_lines:
                    # Attach to the last "other" block if the last block is also "other"
                    if blocks and blocks[-1].category == "other":
                        blocks[-1].lines.extend(blk_lines)
                    else:
                        blocks.append(
                            _StepSubBlock(category="other", name="", lines=blk_lines)
                        )
            else:
                # Keyword line — start a new sub-block
                cat, name = _classify(line)
                blk_lines = [line]
                i += 1
                # Collect data lines up to the next keyword or *End Step.
                # For output blocks, sub-keywords (*Node Output, etc.)
                # are treated as data lines rather than separate blocks.
                while i < len(step_lines):
                    cline = step_lines[i]
                    ctrimmed = cline.lstrip()
                    if inp_parser._is_keyword(cline, "End Step"):
                        break
                    if ctrimmed.startswith("*") and not ctrimmed.startswith("**"):
                        if cat in ("output_field", "output_history") and MergeEngine._is_output_sub_keyword(cline):
                            blk_lines.append(cline)
                            i += 1
                            continue
                        break
                    blk_lines.append(cline)
                    i += 1
                blocks.append(
                    _StepSubBlock(category=cat, name=name, lines=blk_lines)
                )

        return blocks

    # ── Block normalisation for output dedup ──────────────────────

    @staticmethod
    def _block_text(lines: list[str]) -> str:
        """Return a normalised string of block lines for equality comparison."""
        return "\n".join(
            l.rstrip().lower() for l in lines if l.strip()
        )

    # ------------------------------------------------------------------
    #  Phase 6: Merge material/step sections
    # ------------------------------------------------------------------

    def _merge_material_step(
        self,
        output_lines: list[str],
        model1: InpFileModel,
        model2: InpFileModel,
    ) -> None:
        """
        Merge material/step sections from both files.

        Conflict resolution rules:
          - **Material name** duplicates → content-aware: identical content
            dedup, different content rename (``Steel`` → ``Steel_2``)
          - **Step name** duplicates → dedup step header/*Static, but
            merge Boundary/Load/Output content into file1 step (with
            content dedup for outputs)
          - **Boundary name** duplicates → renumber with ``_2`` suffix;
            set references updated via assembly nset name map
          - **Load (Cload etc.) name** duplicates → renumber with ``_2``
            suffix; set references updated via assembly nset name map
          - **Output field/history** duplicates → dedup by content
          - **Restart / Output** (top-level) duplicates → dedup by content

        If *model2* has no material/step section, falls back to writing
        only *model1* content (preserving current behaviour).
        """
        if not model2.material_step_lines:
            output_lines.extend(model1.material_step_lines)
            return

        # ── Parse both sides ───────────────────────────────────────
        blocks1 = self._parse_top_blocks(model1.material_step_lines)
        blocks2 = self._parse_top_blocks(model2.material_step_lines)

        # ── Collect file1 names ────────────────────────────────────
        material_names_1: set[str] = set()
        step_names_1: set[str] = set()
        for blk in blocks1:
            if blk.type == "material":
                material_names_1.add(blk.name)
            elif blk.type == "step":
                step_names_1.add(blk.name)

        # ── Collect sub-block names from file1 for conflict detection ──
        bc_names_1: set[str] = set()      # boundary names from file1
        load_names_1: set[str] = set()     # load names from file1

        for blk in blocks1:
            if blk.type == "step":
                sub_blocks = self._parse_step_sub_blocks(blk.lines)
                for sb in sub_blocks:
                    if sb.category == "boundary" and sb.name:
                        bc_names_1.add(sb.name)
                    elif sb.category == "load" and sb.name:
                        load_names_1.add(sb.name)

        self._log(
            f"  Material/step merge: "
            f"{len(material_names_1)} material(s), "
            f"{len(step_names_1)} step(s) from file 1"
        )
        self._log(
            f"  → {len(bc_names_1)} BC name(s), "
            f"{len(load_names_1)} load name(s) tracked"
        )

        # ── Helper: collect non-duplicate material blocks ──────────
        def _collect_materials(
            blocks: list[_TopBlock], name_filter: set[str]
        ) -> tuple[list[_TopBlock], set[str]]:
            kept_blocks: list[_TopBlock] = []
            seen = name_filter.copy()
            for blk in blocks:
                if blk.type == "material":
                    if blk.name not in seen:
                        seen.add(blk.name)
                        kept_blocks.append(blk)
                elif blk.type != "step":
                    # "other" blocks — pass through as-is
                    kept_blocks.append(blk)
            return kept_blocks, seen

        # ── Helper: collect non-duplicate step blocks ──────────────
        def _collect_steps(
            blocks: list[_TopBlock], name_filter: set[str]
        ) -> list[_TopBlock]:
            kept: list[_TopBlock] = []
            for blk in blocks:
                if blk.type == "step":
                    if blk.name not in name_filter:
                        name_filter.add(blk.name)
                        kept.append(blk)
            return kept

        # ── Separate blocks from both files ───────────────────────
        # Phase 6a: materials (and other non-step) blocks
        # Phase 6b: step blocks
        step_names_all: set[str] = set()
        mat_blocks_all, _ = _collect_materials(blocks1, set())

        # File2 materials: content-aware conflict resolution
        # If name + content identical → dedup; if name same but content different → rename
        mat_blocks_1_by_name: dict[str, _TopBlock] = {}
        for blk in blocks1:
            if blk.type == "material":
                mat_blocks_1_by_name[blk.name] = blk

        f2_mat_blocks: list[_TopBlock] = []
        # Use a separate set for conflict tracking so material_names_1
        # (file1 names) stays unchanged for logging purposes
        seen_material_names: set[str] = material_names_1.copy()
        for blk in blocks2:
            if blk.type == "material":
                if blk.name not in seen_material_names:
                    # No name conflict → keep as-is
                    seen_material_names.add(blk.name)
                    f2_mat_blocks.append(blk)
                else:
                    # Name conflict → compare content
                    existing = mat_blocks_1_by_name.get(blk.name)
                    if (
                        existing is not None
                        and self._block_text(blk.lines)
                        == self._block_text(existing.lines)
                    ):
                        # Identical content → dedup
                        self._log(
                            f"    → Skipping duplicate material:"
                            f" {blk.name} (identical content)"
                        )
                    else:
                        # Different content → rename and keep
                        counter = 2
                        new_name = f"{blk.name}_{counter}"
                        while new_name in seen_material_names:
                            counter += 1
                            new_name = f"{blk.name}_{counter}"
                        # Rename the keyword line
                        blk.lines[0] = blk.lines[0].replace(
                            f"name={blk.name}", f"name={new_name}"
                        )
                        self._log(
                            f"    → Renamed material:"
                            f" {blk.name} → {new_name}"
                        )
                        seen_material_names.add(new_name)
                        f2_mat_blocks.append(blk)
            elif blk.type != "step":
                # "other" blocks — pass through as-is
                f2_mat_blocks.append(blk)

        mat_blocks_all.extend(f2_mat_blocks)

        step_blocks_all = _collect_steps(blocks1, step_names_all)

        # Pre-collect file2 boundary/load/output from steps that will be
        # deduped (same name as file1 step) — these need merging into
        # the file1 step rather than being silently dropped.
        f2_boundary_load_merge: dict[str, list[_StepSubBlock]] = {}
        for blk in blocks2:
            if blk.type == "step" and blk.name in step_names_1:
                sub_blocks = self._parse_step_sub_blocks(blk.lines[1:])
                bl_blocks = [
                    sb
                    for sb in sub_blocks
                    if sb.category in ("boundary", "load", "output_field", "output_history")
                ]
                if bl_blocks:
                    f2_boundary_load_merge[blk.name] = bl_blocks

        f2_step_blocks = _collect_steps(blocks2, step_names_all)
        step_blocks_all.extend(f2_step_blocks)

        # ── Dedup *Restart / *Output top-level blocks ────────────
        _seen_restart_output: set[str] = set()
        _deduped_blocks: list[_TopBlock] = []
        for blk in mat_blocks_all:
            if blk.type == "other" and blk.lines:
                line = blk.lines[0].strip().lower()
                if line.startswith("*restart") or line.startswith("*output"):
                    text = self._block_text(blk.lines)
                    if text in _seen_restart_output:
                        self._log(
                            f"    → Skipping duplicate {blk.lines[0].strip()}"
                        )
                        continue
                    _seen_restart_output.add(text)
            _deduped_blocks.append(blk)
        mat_blocks_all = _deduped_blocks

        # ── Write all materials (plus other non-step blocks) ──────
        for blk in mat_blocks_all:
            if blk.type == "material" and blk.name not in material_names_1:
                self._log(f"    → Added material: {blk.name}")
            output_lines.extend(blk.lines)

        # ── Write all steps with conflict resolution ──────────────
        bc_counters: dict[str, int] = {}
        load_counters: dict[str, int] = {}
        file2_steps_kept = 0

        for blk in step_blocks_all:
            is_from_file2 = blk.name not in step_names_1
            if is_from_file2:
                file2_steps_kept += 1

            # Write *Step line
            output_lines.append(blk.lines[0])

            # Parse step body (skip *Step header line) and apply
            # conflict resolution (file2 only)
            sub_blocks = self._parse_step_sub_blocks(blk.lines[1:])
            _step_outputs: set[str] = set()

            for sb in sub_blocks:
                if is_from_file2 and sb.category == "boundary" and sb.name:
                    # Update set references in data lines before any rename
                    bc_lines = self._update_set_refs_in_block(
                        sb.lines, self._nset_name_map
                    )
                    if sb.name in bc_names_1:
                        bc_counters[sb.name] = bc_counters.get(sb.name, 1) + 1
                        new_name = f"{sb.name}_{bc_counters[sb.name]}"
                        kw_line = bc_lines[0]
                        new_kw_line = kw_line.replace(
                            f"name={sb.name}", f"name={new_name}"
                        )
                        output_lines.append(new_kw_line)
                        output_lines.extend(bc_lines[1:])
                        self._log(
                            f"    → Renamed boundary: {sb.name} → {new_name}"
                        )
                    else:
                        bc_names_1.add(sb.name)
                        output_lines.extend(bc_lines)

                elif is_from_file2 and sb.category == "load" and sb.name:
                    # Update set references in data lines before any rename
                    load_lines = self._update_set_refs_in_block(
                        sb.lines, self._nset_name_map
                    )
                    if sb.name in load_names_1:
                        load_counters[sb.name] = load_counters.get(sb.name, 1) + 1
                        new_name = f"{sb.name}_{load_counters[sb.name]}"
                        kw_line = load_lines[0]
                        new_kw_line = kw_line.replace(
                            f"name={sb.name}", f"name={new_name}"
                        )
                        output_lines.append(new_kw_line)
                        output_lines.extend(load_lines[1:])
                        self._log(
                            f"    → Renamed load: {sb.name} → {new_name}"
                        )
                    else:
                        load_names_1.add(sb.name)
                        output_lines.extend(load_lines)

                elif sb.category in ("output_field", "output_history"):
                    text = self._block_text(sb.lines)
                    if text in _step_outputs:
                        self._log(
                            f"    → Skipping duplicate output: "
                            f"{sb.lines[0].strip()}"
                        )
                    else:
                        _step_outputs.add(text)
                        output_lines.extend(sb.lines)

                else:
                    output_lines.extend(sb.lines)

            # Merge file2 boundary/load/output into matching file1 step
            # (when file2 step was deduped, its content must survive)
            # Group by category: Boundary first, then Load, then Output
            if not is_from_file2 and blk.name in f2_boundary_load_merge:
                merged_sbs = f2_boundary_load_merge[blk.name]

                boundary_blocks = [
                    sb for sb in merged_sbs if sb.category == "boundary"
                ]
                load_blocks = [
                    sb for sb in merged_sbs if sb.category == "load"
                ]
                output_blocks = [
                    sb
                    for sb in merged_sbs
                    if sb.category in ("output_field", "output_history")
                ]

                # Pass 1: All Boundary blocks
                for sb in boundary_blocks:
                    updated_lines = self._update_set_refs_in_block(
                        sb.lines, self._nset_name_map
                    )
                    if sb.name:
                        if sb.name in bc_names_1:
                            bc_counters[sb.name] = (
                                bc_counters.get(sb.name, 1) + 1
                            )
                            new_name = (
                                f"{sb.name}_{bc_counters[sb.name]}"
                            )
                            kw_line = updated_lines[0]
                            new_kw_line = kw_line.replace(
                                f"name={sb.name}", f"name={new_name}"
                            )
                            output_lines.append(new_kw_line)
                            output_lines.extend(updated_lines[1:])
                            self._log(
                                f"    → Renamed boundary (merged): "
                                f"{sb.name} → {new_name}"
                            )
                        else:
                            bc_names_1.add(sb.name)
                            output_lines.extend(updated_lines)
                    else:
                        # Nameless boundary — add as-is
                        output_lines.extend(updated_lines)

                # Pass 2: All Load blocks
                for sb in load_blocks:
                    updated_lines = self._update_set_refs_in_block(
                        sb.lines, self._nset_name_map
                    )
                    if sb.name:
                        if sb.name in load_names_1:
                            load_counters[sb.name] = (
                                load_counters.get(sb.name, 1) + 1
                            )
                            new_name = (
                                f"{sb.name}_{load_counters[sb.name]}"
                            )
                            kw_line = updated_lines[0]
                            new_kw_line = kw_line.replace(
                                f"name={sb.name}", f"name={new_name}"
                            )
                            output_lines.append(new_kw_line)
                            output_lines.extend(updated_lines[1:])
                            self._log(
                                f"    → Renamed load (merged): "
                                f"{sb.name} → {new_name}"
                            )
                        else:
                            load_names_1.add(sb.name)
                            output_lines.extend(updated_lines)
                    else:
                        # Nameless load — add as-is
                        output_lines.extend(updated_lines)

                # Pass 3: All Output blocks (content dedup against file1 step)
                for sb in output_blocks:
                    text = self._block_text(sb.lines)
                    if text in _step_outputs:
                        self._log(
                            f"    → Skipping duplicate output (merged): "
                            f"{sb.lines[0].strip()}"
                        )
                    else:
                        _step_outputs.add(text)
                        output_lines.extend(sb.lines)

            # Write *End Step
            if len(blk.lines) > 1 and inp_parser._is_keyword(
                blk.lines[-1], "End Step"
            ):
                output_lines.append(blk.lines[-1])

        self._log(
            f"  Phase 6 complete: +{len(f2_mat_blocks)} material(s), "
            f"+{file2_steps_kept} step(s) from file 2"
        )

    # ------------------------------------------------------------------
    #  Synchronous wrapper (for use in QThreadPool / testing)
    # ------------------------------------------------------------------

    def merge_sync(
        self,
        file1_path: str,
        file2_path: str,
        output_path: str,
    ) -> MergeResult:
        """Synchronous wrapper for use outside an async event loop."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run, self.merge(file1_path, file2_path, output_path)
                )
                return future.result()
        else:
            return asyncio.run(self.merge(file1_path, file2_path, output_path))

    # ------------------------------------------------------------------
    #  Helper: update set name references in boundary/load data lines
    # ------------------------------------------------------------------

    @staticmethod
    def _update_set_refs_in_block(
        lines: list[str], name_map: dict[str, str]
    ) -> list[str]:
        """Replace renamed set references in boundary/load block data lines.

        For each data line after the keyword line, replace occurrences of
        old set names (keys in *name_map*) with their renamed counterparts
        (values in *name_map*).

        Args:
            lines: Raw block lines (keyword + data).
            name_map: Mapping of old → new set names (from assembly nsets).

        Returns:
            Updated block lines with replaced set references.
        """
        if not name_map or not lines:
            return list(lines)
        result: list[str] = [lines[0]]  # keyword line stays as-is
        for data_line in lines[1:]:
            new_line = data_line
            for old_name, new_name in name_map.items():
                new_line = new_line.replace(old_name, new_name)
            result.append(new_line)
        return result

    # ------------------------------------------------------------------
    #  Nset helper
    # ------------------------------------------------------------------

    @staticmethod
    def _write_nset(
        output_lines: list[str],
        nset: InpSet,
        id_offset: int,
        name: str,
        instance_name_map: dict[str, str] | None = None,
    ) -> None:
        """Write a single Nset to *output_lines* with optional ID offset.

        Args:
            output_lines: Target line list.
            nset: The nset to write.
            id_offset: Offset added to node IDs.
            name: The (possibly renamed) set name to write.
            instance_name_map: Optional map of old→new instance names for
                               updating ``instance=`` references.
        """
        if nset.is_generate:
            output_lines.append(f"*Nset, nset={name}, generate")
            output_lines.append(
                f"{nset.start + id_offset}, {nset.end + id_offset}, {nset.step}"
            )
        elif nset.keyword_line:
            # Preserve original keyword parameters (instance=, internal, etc.)
            kw = nset.keyword_line
            if nset.name:
                kw = kw.replace(f"nset={nset.name}", f"nset={name}")
            if instance_name_map:
                inst = MergeEngine._get_param(kw, "instance")
                if inst in instance_name_map:
                    kw = kw.replace(
                        f"instance={inst}", f"instance={instance_name_map[inst]}"
                    )
            output_lines.append(kw)
            offset_ids = [i + id_offset for i in nset.ids]
            output_lines.extend(MergeEngine._write_id_lines(offset_ids))
        else:
            output_lines.append(f"*Nset, nset={name}")
            offset_ids = [i + id_offset for i in nset.ids]
            output_lines.extend(MergeEngine._write_id_lines(offset_ids))
