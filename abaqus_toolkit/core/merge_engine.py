"""
Merge engine for combining two Abaqus INP files via a 6-phase pipeline.

6-phase pipeline:
  Phase 1: Read + parse file1, compute node/element offsets from max IDs
  Phase 2: Write file1 heading lines to output
  Phase 3: Write file1 parts (offset=0, no renumbering)
  Phase 4: Read + parse file2, write parts (renumbered with offsets)
  Phase 5: Write merged Assembly (instances, ref nodes, nsets, elsets,
           surfaces, couplings with conflict resolution & renaming)
  Phase 6: Write file1 material/step lines to output

Maps 1:1 from the C# InpMergeService.WriteAssembly logic.
"""

from pathlib import Path
from typing import Callable, Optional

from . import inp_parser, inp_writer
from .models import InpAssemblyElset, InpCoupling, InpFileModel, InpInstance, InpNode, InpSet, InpSurface, MergeResult


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

            # Phase 6: Write material/step
            self._log("Phase 6: Writing material/step...")
            output_lines.extend(model1.material_step_lines)

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
        # File 1 instances (as-is)
        for inst in model1.assembly_instances:
            output_lines.append(f"*Instance, name={inst.name}, part={inst.part_name}")
            if inst.has_offset:
                output_lines.append(
                    f"       {inst.offset_x:g}, {inst.offset_y:g}, {inst.offset_z:g}"
                )
            output_lines.append("*End Instance")
            output_lines.append("**  ")
            instance_count += 1

        # File 2 instances (update part= if that part was renamed)
        for inst in model2.assembly_instances:
            part_name = (
                inst.part_name + "-2"
                if inst.part_name in file1_part_names
                else inst.part_name
            )
            output_lines.append(f"*Instance, name={inst.name}, part={part_name}")
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

            # Replace elset=... in the keyword line with renamed value
            new_keyword_line = elset.keyword_line.replace(
                f"elset={elset.name}", f"elset={new_name}"
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
