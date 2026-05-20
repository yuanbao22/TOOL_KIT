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
from .models import InpAssemblyElset, InpCoupling, InpFileModel, InpInstance, InpNode, InpSet, InpSurface, MergeResult


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

            self._log("Phase 4: Writing file2 parts (renumbered)...")
            for part in model2.parts:
                if part.name in existing_names:
                    part.name += "-2"
                output_lines.extend(inp_writer.write_part(part, node_offset, elem_offset))
            self._log(
                f"  {len(model2.parts)} part(s) written from file 2 "
                f"(nodes +{node_offset}, elements +{elem_offset})"
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
            self._write_nset(output_lines, nset, node_offset, new_name)

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

            output_lines.append(f"*Surface, type={surf.type}, name={new_name}")
            for entry in surf.entries:
                new_elset_name = elset_name_map.get(entry.elset_name, entry.elset_name)
                output_lines.append(f"{new_elset_name}, {entry.face_label}")

        # --- Couplings --------------------------------------------------
        # File 1 couplings
        coupling_name_counts: dict[str, int] = {}
        for coupling in model1.assembly_couplings:
            coupling_name_counts[coupling.name] = 1
            output_lines.append(
                f"*Coupling, constraint name={coupling.name}, "
                f"ref node={coupling.ref_node_set}, surface={coupling.surface}"
            )
            output_lines.append(coupling.constraint_type)

        # File 2 couplings (rename duplicates, remap surface & ref node)
        for coupling in model2.assembly_couplings:
            new_name = coupling.name
            new_surface = coupling.surface
            new_ref_node = coupling.ref_node_set

            if coupling.name in coupling_name_counts:
                coupling_name_counts[coupling.name] += 1
                new_name = f"{coupling.name}_{coupling_name_counts[coupling.name]}"
            else:
                coupling_name_counts[coupling.name] = 1

            # Remap references through name maps
            new_surface = surface_name_map.get(coupling.surface, coupling.surface)
            new_ref_node = nset_name_map.get(coupling.ref_node_set, coupling.ref_node_set)

            output_lines.append(
                f"*Coupling, constraint name={new_name}, "
                f"ref node={new_ref_node}, surface={new_surface}"
            )
            output_lines.append(coupling.constraint_type)

        # Footer
        output_lines.append("*End Assembly")

        surface_total = len(surface_name_counts)
        coupling_total = len(coupling_name_counts)
        self._log(
            f"  Assembly written: {instance_count} instance(s), "
            f"{surface_total} surface(s), {coupling_total} constraint(s)"
        )

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

    # ------------------------------------------------------------------
    #  Material/step block parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_top_blocks(lines: list[str]) -> list[_TopBlock]:
        """
        Split raw material/step lines into top-level blocks.

        Recognised blocks:
          - ``*Material, name=...``  (type ``"material"``)
          - ``*Step, name=...`` ... ``*End Step``  (type ``"step"``)
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
                while i < len(lines) and not _is_material(lines[i]) and not _is_step(lines[i]):
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
          - **Material name** duplicates → dedup (keep first only)
          - **Step name** duplicates → dedup (keep first only)
          - **Boundary name** duplicates → renumber with ``_2`` suffix
          - **Load name** duplicates → renumber with ``_2`` suffix
          - **Output field/history** duplicates → dedup by content

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

        # ── Phase 6a: Write file1 blocks unchanged ────────────────
        for blk in blocks1:
            output_lines.extend(blk.lines)

        # ── Phase 6b: Write file2 blocks with conflict resolution ──
        bc_counters: dict[str, int] = {}
        load_counters: dict[str, int] = {}

        file2_materials_kept = 0
        file2_steps_kept = 0

        for blk in blocks2:
            if blk.type == "material":
                if blk.name not in material_names_1:
                    output_lines.extend(blk.lines)
                    file2_materials_kept += 1
                else:
                    self._log(f"    → Skipping duplicate material: {blk.name}")

            elif blk.type == "step":
                if blk.name in step_names_1:
                    self._log(f"    → Skipping duplicate step: {blk.name}")
                    continue

                # Write *Step line
                output_lines.append(blk.lines[0])
                file2_steps_kept += 1

                # Parse step body (skip *Step header line) and apply
                # conflict resolution
                sub_blocks = self._parse_step_sub_blocks(blk.lines[1:])
                _step_outputs: set[str] = set()  # per-step output dedup

                for sb in sub_blocks:
                    if sb.category == "boundary" and sb.name:
                        if sb.name in bc_names_1:
                            bc_counters[sb.name] = bc_counters.get(sb.name, 1) + 1
                            new_name = f"{sb.name}_{bc_counters[sb.name]}"
                            # Rename in the keyword line
                            kw_line = sb.lines[0]
                            new_kw_line = kw_line.replace(
                                f"name={sb.name}", f"name={new_name}"
                            )
                            output_lines.append(new_kw_line)
                            output_lines.extend(sb.lines[1:])
                            self._log(
                                f"    → Renamed boundary: {sb.name} → {new_name}"
                            )
                        else:
                            bc_names_1.add(sb.name)
                            output_lines.extend(sb.lines)

                    elif sb.category == "load" and sb.name:
                        if sb.name in load_names_1:
                            load_counters[sb.name] = load_counters.get(sb.name, 1) + 1
                            new_name = f"{sb.name}_{load_counters[sb.name]}"
                            kw_line = sb.lines[0]
                            new_kw_line = kw_line.replace(
                                f"name={sb.name}", f"name={new_name}"
                            )
                            output_lines.append(new_kw_line)
                            output_lines.extend(sb.lines[1:])
                            self._log(
                                f"    → Renamed load: {sb.name} → {new_name}"
                            )
                        else:
                            load_names_1.add(sb.name)
                            output_lines.extend(sb.lines)

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
                        # "other" or unnamed sub-blocks — pass through
                        output_lines.extend(sb.lines)

                # Write *End Step (last line of the original step block)
                if len(blk.lines) > 1 and inp_parser._is_keyword(
                    blk.lines[-1], "End Step"
                ):
                    output_lines.append(blk.lines[-1])

            else:
                # "other" blocks — pass through as-is
                output_lines.extend(blk.lines)

        self._log(
            f"  Phase 6 complete: +{file2_materials_kept} material(s), "
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
    #  Nset helper
    # ------------------------------------------------------------------

    @staticmethod
    def _write_nset(
        output_lines: list[str],
        nset: InpSet,
        id_offset: int,
        name: str,
    ) -> None:
        """Write a single Nset to *output_lines* with optional ID offset."""
        if nset.is_generate:
            output_lines.append(f"*Nset, nset={name}, generate")
            output_lines.append(
                f"{nset.start + id_offset}, {nset.end + id_offset}, {nset.step}"
            )
        else:
            output_lines.append(f"*Nset, nset={name}")
            offset_ids = [i + id_offset for i in nset.ids]
            output_lines.extend(MergeEngine._write_id_lines(offset_ids))
