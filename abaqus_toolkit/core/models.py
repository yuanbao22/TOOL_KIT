"""
Data models for Abaqus INP file processing.
All models use @dataclass for clean, boilerplate-free definitions.

Maps 1:1 from the C# AbaqusToolkit.Core.Models namespace.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class InpNode:
    """A single node definition: id, x, y, z coordinates."""

    id: int
    x: float
    y: float
    z: float


@dataclass
class InpElement:
    """A single element definition: id, connected node IDs."""

    id: int
    node_ids: list[int] = field(default_factory=list)


@dataclass
class InpSet:
    """
    Represents a node set (Nset) or element set (Elset).
    Supports both 'generate' mode (start/end/step) and explicit ID lists.
    """

    name: str = ""
    is_generate: bool = False
    start: int = 0
    end: int = 0
    step: int = 0
    ids: list[int] = field(default_factory=list)
    keyword_line: str = ""  # original keyword line, preserves instance=/internal


@dataclass
class InpOrientation:
    """An orientation definition inside a Part block."""

    name: str = ""
    lines: list[str] = field(default_factory=list)


@dataclass
class InpPart:
    """Represents a Part section (*Part ... *End Part) in an INP file."""

    name: str = ""
    element_type: str = ""
    nodes: list[InpNode] = field(default_factory=list)
    elements: list[InpElement] = field(default_factory=list)
    element_blocks: list[tuple[str, list[InpElement]]] = field(default_factory=list)
    """Element blocks grouped by type. Each entry: (type_str, elements_list).
    Populated during parsing to preserve per-block element types.
    Falls back to [(element_type, elements)] when empty."""
    nsets: list[InpSet] = field(default_factory=list)
    elsets: list[InpSet] = field(default_factory=list)
    orientations: list[InpOrientation] = field(default_factory=list)
    solid_section_lines: list[str] = field(default_factory=list)
    shell_section_lines: list[str] = field(default_factory=list)
    unknown_block_lines: list[list[str]] = field(default_factory=list)
    """Preserved unknown keyword blocks (e.g. *Beam Section, *Spring, etc.).
    Each entry is a list of lines: [keyword_line, data_line_1, ...]."""


@dataclass
class InpInstance:
    """Represents an Instance definition within the Assembly section."""

    name: str = ""
    part_name: str = ""
    offset_x: float = 0.0
    offset_y: float = 0.0
    offset_z: float = 0.0
    has_offset: bool = False


@dataclass
class InpAssemblyElset:
    """
    Represents an element set (Elset) within the Assembly section.
    May include instance= parameter referencing a specific Instance.
    """

    name: str = ""
    instance_name: Optional[str] = None
    is_generate: bool = False
    is_internal: bool = False
    start: int = 0
    end: int = 0
    step: int = 0
    ids: list[int] = field(default_factory=list)
    keyword_line: str = ""
    data_lines: list[str] = field(default_factory=list)


@dataclass
class InpSurfaceEntry:
    """A single face entry within a surface definition (e.g. '_s_Surf-1_S1, S1')."""

    elset_name: str = ""
    face_label: str = ""


@dataclass
class InpSurface:
    """Represents a surface definition (*Surface) within the Assembly section."""

    name: str = ""
    type: str = ""
    entries: list[InpSurfaceEntry] = field(default_factory=list)
    keyword_line: str = ""  # original keyword line, preserves internal etc.


@dataclass
class InpCoupling:
    """Represents a coupling constraint (*Coupling) within the Assembly section."""

    name: str = ""
    ref_node_set: str = ""
    surface: str = ""
    constraint_type: str = ""


@dataclass
class InpConstraint:
    """A generic constraint definition in the Assembly section.

    Covers *Tie, *Rigid Body, *Display Body, *Coupling, and any other
    constraint keyword. Stores raw lines for faithful reproduction.
    """

    type: str = ""           # e.g. "Tie", "Rigid Body", "Coupling", "Display Body"
    name: str = ""           # name= (or constraint name= for Coupling)
    keyword_line: str = ""   # full original keyword line
    data_lines: list[str] = field(default_factory=list)
    """Lines after the keyword: data lines + sub-keywords (e.g. *Kinematic)."""


@dataclass
class InpFileModel:
    """
    Top-level model representing a complete parsed INP file.
    Contains both structured data and raw passthrough sections.
    """

    heading_lines: list[str] = field(default_factory=list)
    parts: list[InpPart] = field(default_factory=list)
    assembly_name: str = ""
    assembly_instances: list[InpInstance] = field(default_factory=list)
    assembly_ref_nodes: list[InpNode] = field(default_factory=list)
    assembly_nsets: list[InpSet] = field(default_factory=list)
    assembly_elsets: list[InpAssemblyElset] = field(default_factory=list)
    assembly_surfaces: list[InpSurface] = field(default_factory=list)
    assembly_couplings: list[InpCoupling] = field(default_factory=list)
    assembly_constraints: list[InpConstraint] = field(default_factory=list)
    """All constraint definitions (*Tie, *Rigid Body, *Coupling, *Display Body, etc.)."""
    assembly_lines: list[str] = field(default_factory=list)
    assembly_unknown_blocks: list[list[str]] = field(default_factory=list)
    """Preserved unknown keyword blocks in Assembly (e.g. *Element, type=MASS
    + data lines, *Mass, *Spring, etc.). Each entry is [keyword, data_1, ...]."""
    material_step_lines: list[str] = field(default_factory=list)


@dataclass
class MergeResult:
    """Result data transfer object for INP merge operations."""

    success: bool = False
    output_path: str = ""
    message: str = ""
    log_lines: list[str] = field(default_factory=list)
    node_offset: int = 0
    elem_offset: int = 0
