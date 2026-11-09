"""cmjsc - cell morphometry from JSC data.

Turns the H5 files of a JSC cell-segmentation job (celldetection-inference,
Eric Upschulte's jobbox) into the canonical per-ROI structure

    <roi>_CellSegmentations.zip   per-cell instance masks (label layers)
    <roi>_CellInstances.tsv.gz    one row per cell (feature set from config)

with complete provenance (input paths, SHA-256, git commit, parameters), so the
large H5 files can be archived and deleted.
"""

__version__ = "1.1.0"
